# Ingestion design

Source: `backend/worker/ingestion/{discovery,pipeline,cost_details}.py`,
`backend/worker/export_processing/{schema,normalizer}.py`, `backend/worker/aggregation/rebuild.py`,
`backend/app/services/job_service.py`, `backend/worker/main.py`.

## Jobs

The worker processes rows of `ingestion_jobs`:

| `job_type` | Created by | Does |
|---|---|---|
| `sync_subscription` | scheduler (every `EXPORT_DISCOVERY_INTERVAL_MINUTES`), `POST /ingestion/trigger` | discover & ingest new runs for one subscription |
| `reprocess_subscription` | `POST /ingestion/reprocess` | re-ingest runs overlapping a date range with `force=true` |
| `backfill_cost_details` | `POST /ingestion/backfill` | Cost Details API report → pipeline |
| `reattribute` | `POST /admin/reattribute` | re-apply allocation / category rules to stored rows, rebuild aggregates |
| `analytics` | after any job that applied runs; scheduler every `ANALYTICS_INTERVAL_MINUTES`; `POST /ingestion/analytics` | anomalies → savings → budget/forecast snapshots → notifications |
| `advisor_import` | scheduler with each analytics run when `AZURE_AUTH_MODE` ≠ `disabled`; `POST /ingestion/advisor` | import Azure Advisor cost recommendations |
| `retention` | scheduler daily | drop raw billing partitions older than `retention.cost_records_months` |

- **Claiming**: `UPDATE … SET status='running' WHERE id = (SELECT id … WHERE status='queued' AND next_attempt_at <= now() ORDER BY priority, id FOR UPDATE SKIP LOCKED LIMIT 1)`. Any number of workers can run.
- **De-duplication**: enqueueing returns the existing queued/running job with the same type, subscription, dataset and params (no repeated Azure requests).
- **Retries**: on failure the job is re-queued with `next_attempt_at = now + JOB_RETRY_BACKOFF_SECONDS × 2^(attempts-1)` until `JOB_MAX_ATTEMPTS`; then `failed` and an *ingestion failure* notification is raised. `POST /ingestion/retry/{id}` resets attempts.
- **Stale jobs**: every 5 minutes, `running` jobs locked longer than `JOB_STALE_AFTER_MINUTES` are re-queued.
- **Scheduler leader**: one worker holds `pg_try_advisory_lock(778899)` on a dedicated connection and is the only one enqueueing periodic jobs.
- **Isolation**: one job per subscription; export definitions and runs are processed independently, so one subscription's failure never blocks another.
- **Heartbeat**: `/tmp/acip-worker-heartbeat` is written each loop; `python -m worker.healthcheck` (liveness) fails if it is older than `WORKER_HEARTBEAT_MAX_AGE` (300 s).

## Run processing (`process_run`)

1. **Register** the run in `export_runs` (unique per definition + run key). Runs already
   `applied` / `superseded` / `skipped_duplicate` / `skipped_empty` are skipped unless `force`.
   Runs whose manifest lists files not yet delivered stay `discovered` (retried next sync).
2. **Download** each file to a temp directory, computing **SHA-256** while streaming.
3. **Duplicate check**: if *every* file's hash was already processed for this export definition,
   the run is `skipped_duplicate` (nothing re-ingested).
4. **Parse & normalise** (single DB transaction from here on): `build_mapping` detects the schema;
   missing required columns (`usage_date`, a cost column) fail the run. Each row is normalised
   (`NORMALIZER_VERSION`), checked against the run's declared period (`out_of_period`), allocated
   by `AllocationEngine`, and written with `COPY` to `cost_records_staging`. Rejected rows are
   counted; the first 200 per file are stored in `ingestion_errors`.
5. **Validate completeness**: manifest `dataRowCount` must equal rows read; rejected rows must not
   exceed `INGESTION_REJECT_THRESHOLD_PCT` (default 1 %). An empty run (0 rows) is
   `skipped_empty` and leaves existing data untouched (protects against broken exports).
6. **Apply** (`apply_run`):
   - `pg_advisory_xact_lock(subscription_fk, dataset)` serialises applies per slice;
   - monthly partitions for the period are created if missing;
   - *blocked days* = days in the period whose `cost_data_slices.run_submitted_at` is **newer**
     than this run (ignored with `force`);
   - `DELETE` existing `cost_records` for the period except blocked days; `INSERT … SELECT` the
     staged rows for the same days;
   - upsert `cost_data_slices` for every applied day (including days with zero rows, so a
     revision that removes a day really removes it);
   - rebuild aggregates for the applied range; upsert `azure_resources` and `resource_groups`
     (latest attributes win only when the run's data is at least as recent);
   - mark earlier runs whose days are all replaced as `superseded`;
   - delete the run's staging rows.
   Final status: `applied`, `partially_applied` (some days blocked) or `superseded` (all blocked).
7. On any error the transaction rolls back (staging rows vanish too), the run is `failed` with the
   message, and errors are recorded. Existing reporting data is unchanged.

### Why replace-by-slice

Month-to-date exports are cumulative snapshots and Azure revises recent days. Appending would
double count; hashing rows to de-duplicate would collapse legitimately identical rows. Replacing
the run's declared period per (subscription, dataset) — with "newer submission wins" per day —
makes re-processing, revisions and out-of-order arrival all safe and idempotent.

## Reprocessing and backfill

- **Reprocess** (`POST /ingestion/reprocess`): re-ingests runs overlapping the range with
  `force=true` (e.g. after a normaliser change).
- **Re-attribute** (`POST /admin/reattribute`): recomputes allocation on stored rows (per distinct
  attribute combination) and rebuilds all aggregates for the subscription(s).
- **Historical backfill**: either keep older export runs in storage (the first sync ingests all of
  them, oldest period first) or use the Cost Details API backfill (one month per request).

## Data freshness

`GET /api/v1/meta/freshness` (header indicator) and `/ingestion/status` derive per subscription:
`demo`, `processing` (queued/running job), `awaiting_export` (no data, no error), `failed`
(latest attempt failed), `delayed` (latest usage date older than
`freshness.delay_threshold_hours`, default 48 h), `fresh`; overall `partial` when some
subscriptions are fresh and others are not. The latest *usage date* and the last successful
*ingestion* are always shown separately — no status implies real-time data. Current-month data is
labelled as estimated until the invoice closes.

## Demo mode

`python -m app.cli init` (first start with `DEMO_MODE=true`) or `python -m app.cli seed-demo`
generates synthetic export files (`app/demo/generator.py`) under
`$LOCAL_EXPORT_ROOT/cost-exports/demo/<subscription>/<dataset>/acip-<dataset>-daily/…` and ingests
them through this exact pipeline (export definitions with `storage_account_url = local://demo`).
It includes a revised month-to-date run to exercise replace/supersede behaviour.
