# Database design

PostgreSQL 16. Schema is managed by **Alembic** (`backend/migrations/versions/0001_initial_schema.py`).
A reference dump is kept in `database/schema/schema.sql` (regenerate after migrations —
see `database/README.md`). Monetary columns are `NUMERIC(28,10)`; quantities `NUMERIC(28,10)`;
rounding happens only at presentation.

## Configuration

| Table | Purpose |
|---|---|
| `applications` | Business applications (code, name, owner, sort order, `is_demo`). |
| `environments` | `production`, `non_production`, `development`, `testing`, `uat`, `shared`, `unallocated` with an `environment_group` (production / non_production / shared / unallocated) used by the global environment filter. Seeded. |
| `azure_subscriptions` | Registered subscriptions: GUID, name, application, environment, tenant, billing currency, enabled, `is_demo`, connection-test state (`auth_status`, `cost_api_status`, `storage_status`, `connection_status`, `connection_details`), sync state (`last_successful_sync_at`, `last_sync_attempt_at`, `last_sync_error`). |
| `export_definitions` | Cost Management exports ingested per subscription: dataset (`actual` / `amortized` / `focus`), export name, container, root folder, optional storage URL (`local://…` = local directory), discovery state. Unique (subscription, dataset, export name). |
| `resource_groups` | Inventory derived from billing (first/last seen). |
| `azure_resources` | Resource inventory derived from billing: lower-cased ARM id (`resource_key`, unique), name, type, region, SKU, tags, latest attribution, first/last seen date. |
| `resource_tag_mappings` | Tag → dimension rules (owner, cost_center, project, team, business_unit, workload, application, environment) with priority. |
| `application_mappings` | Resource-group / resource-id glob rules → application, environment and allocation status (`allocated` / `shared` / `unallocated`). |
| `service_category_rules` | Classification of billing rows into reporting service categories (first match by priority; default rules seeded). |

## Cost facts

| Table | Purpose |
|---|---|
| `cost_records` | Normalised export rows. **Range-partitioned by month on `usage_date`** (`cost_records_YYYY_MM`, created on demand by the worker; `cost_records_default` exists as a safety net and should stay empty). PK `(id, usage_date)`; id from sequence `cost_records_id_seq`. Keeps source traceability: `export_run_id`, `ingestion_file_id`, `source_row_number`, `normalizer_version`, unmapped columns in `extra` (JSONB). |
| `cost_records_staging` | UNLOGGED scratch table with the same columns (minus `id`, `ingested_at`), loaded with `COPY`, emptied per run inside the apply transaction. |
| `cost_data_slices` | One row per (subscription, dataset, usage_date): which export run supplied that day and that run's submission time. Enforces "newer run wins". |

Indexes on `cost_records` (partitioned indexes): `(subscription_fk, dataset_type, usage_date)`,
`(resource_key, dataset_type, usage_date)`, `(export_run_id)`, `(ingestion_file_id)`.

## Reporting aggregates

All share the same dimension column names as `cost_records` so one query builder can target any of them.

| Table | Grain | Extra dimensions | Typical use |
|---|---|---|---|
| `monthly_cost_aggregates` | month (`usage_date` = 1st) | coarse dims | whole-month ranges at monthly granularity |
| `daily_cost_aggregates` | day | dataset, currency, subscription, application, environment, allocation status, service category, region, charge type, pricing model, owner, cost center, is_demo | KPIs, trends, most breakdowns |
| `resource_cost_aggregates` | day × resource | + resource key/name/group/type, tags | resource tables, tag grouping, resource filters, search |
| `meter_cost_aggregates` | day × resource × meter × charge type × pricing model | + meter id/category/subcategory/name, unit, SKU, quantity | meter analysis, price/volume decomposition |

Views: `weekly_cost_aggregates` (weekly buckets honouring `reporting.week_start_isodow` from
`application_settings`) and `service_cost_aggregates` (monthly × service). The API itself
buckets weeks from daily data so the configurable week start always applies.

**Table selection** (`app/repositories/cost_repository.py: choose_table`): the coarsest table whose
dimension set contains every requested group-by and filter dimension; `monthly` only when all
periods are whole months and granularity is monthly or none; `cost_records` (raw) only for
combinations that are not pre-aggregated (e.g. tag + meter) and for billing-record drill-down.

**Rebuild** (`worker/aggregation/rebuild.py`): for each applied (subscription, dataset, date range)
the daily / resource / meter rows are deleted and re-inserted from `cost_records`, and the monthly
rows of the affected months are rebuilt from the daily table — inside the same transaction that
replaced the raw rows, so reports never see raw and aggregate data disagree.

## Ingestion registry

| Table | Purpose |
|---|---|
| `ingestion_jobs` | Background work queue *and* history: type, status (`queued`/`running`/`succeeded`/`failed`), subscription, params, priority, attempts/max, `next_attempt_at`, lock owner, progress, result, error. Index `(status, next_attempt_at, priority)`. |
| `export_runs` | One row per discovered run: run key, declared period, submitted time, manifest, status (`discovered`, `processing`, `applied`, `partially_applied`, `superseded`, `skipped_duplicate`, `skipped_empty`, `failed`), row counts, total cost, days applied / skipped as newer. |
| `ingestion_files` | Every source file: blob path, size, SHA-256 `content_hash`, ETag, status, rows read/loaded/rejected, control total, detected schema, source columns, column mapping, normaliser version. Unique (definition, path, hash). |
| `ingestion_errors` | Row-level data-quality errors (first 200 per file) and run failures. |
| `ingestion_audit_logs` | Per-operation audit trail of the worker (discover, process_run, …). |

## Analytics

| Table | Purpose |
|---|---|
| `anomaly_rules` | Transparent rule definitions (detection type, scope level, filters, thresholds). Seeded with 7 rules. |
| `cost_anomalies` | Detected anomalies (episode-merged): rule, scope key, detection/last-detected date, period, previous/current/baseline cost, absolute and % increase, severity, status, evidence JSON, factual explanation, recommended steps, occurrence count. |
| `anomaly_events` | Detection, re-detection, status changes and comments. |
| `budgets` | Budgets by scope (total / application / subscription / environment / resource group), monthly or annual, currency, cost type, thresholds, forecast alert flag. |
| `forecast_records` | Daily forecast snapshots per budget (written by the analytics job). |
| `savings_opportunities` | Evidence-based opportunities (billing analysis or Azure Advisor), estimated monthly savings (nullable), assumptions, status. |
| `cost_comparisons` | Saved comparison views (parameters only, re-run against current data) — `GET/POST/DELETE /api/v1/costs/saved-comparisons`. |

## Administration

`users`, `roles` (administrator, finops_analyst, engineering_lead, viewer, each mapped to an
Entra app role value), `user_role_assignments` (optionally scoped to one application),
`alert_rules`, `notification_history` (unique `dedup_key`), `audit_logs`,
`application_settings` (runtime business settings; defaults in `app/services/settings_service.py`).

## Currency and cost type

Every billing row keeps its `billing_currency`; every row and aggregate carries `dataset_type`.
Reporting queries always filter to exactly one of each. No exchange-rate conversion is applied.

## Retention

`application_settings.retention.cost_records_months` (default 37, `0` disables) controls raw
retention. The worker schedules a daily `retention` job (`worker/aggregation/retention.py`) that
drops whole monthly `cost_records_YYYY_MM` partitions older than the window. Only raw rows are
removed: the daily / resource / meter / monthly aggregates are independent once built, so
long-range reporting is unaffected (drill-down to individual billing records is only possible
inside the window). Run it on demand with `python -m app.cli retention`.

## Migrations

```bash
docker compose run --rm init python -m app.cli migrate     # local
helm upgrade …                                             # AKS: pre-upgrade hook runs `python -m app.cli migrate`
```

New migrations: `alembic revision --autogenerate -m "…"` inside the backend container
(`backend/migrations/env.py` excludes the partitions and staging table from autogenerate).
