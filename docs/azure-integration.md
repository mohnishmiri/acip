# Azure integration

## One existing service principal

All cost collection uses the **existing** Microsoft Entra application registration / service
principal, for every subscription. No per-subscription identities and no new app registrations
are created for collection.

| Mode (`AZURE_AUTH_MODE`) | Where | Credential (`app/integrations/azure_auth/credentials.py`) |
|---|---|---|
| `disabled` (default) | Local demo | No Azure calls; demo data from generated export files. |
| `client_secret` | Local Docker against real Azure | `ClientSecretCredential(AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET)` |
| `workload_identity` | AKS | `WorkloadIdentityCredential` — the app registration is federated with the Kubernetes service account; the webhook injects `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_FEDERATED_TOKEN_FILE`. No secret in the cluster. |
| `managed_identity` / `default` | Optional | `ManagedIdentityCredential` / `DefaultAzureCredential` |

`azure-identity` caches and renews tokens. Tokens and secrets never reach the browser; the
connections API reports only *whether* a secret is configured.

## Permissions (least privilege)

| Capability | Role | Scope | Used by |
|---|---|---|---|
| Read Cost Management data (connection probe, list exports, Cost Details API backfill) | **Cost Management Reader** | each subscription | API connection test, worker backfill |
| Read export files | **Storage Blob Data Reader** | export storage account (or container) | worker ingestion, API storage check |
| Database URL from Key Vault (AKS) | **Key Vault Secrets User** | ACIP Key Vault | Secrets Store CSI driver |
| Azure Advisor cost recommendations, Activity Log evidence (optional) | **Reader** | each subscription | resource activity endpoint, Advisor import job |

Owner or Contributor is **never** required. Creating exports is an administrator task
(`infrastructure/scripts/create-cost-exports.sh`) needing *Cost Management Contributor* on the
subscription and *Storage Blob Data Contributor* for the export's managed identity — ACIP itself
only reads exports. Assign the read roles with `infrastructure/scripts/assign-roles.sh`.

## Exports

Create, per subscription, daily **MonthToDate** exports for `ActualCost` and `AmortizedCost`
(and monthly **TheLastMonth** exports to capture final revisions of the closed month):

| Export name | Type | Timeframe | Root folder | ACIP export definition |
|---|---|---|---|---|
| `acip-actual-daily` | ActualCost | MonthToDate, daily | `subscriptions/<sub>/actual` | registered by default |
| `acip-amortized-daily` | AmortizedCost | MonthToDate, daily | `subscriptions/<sub>/amortized` | registered by default |
| `acip-actual-lastmonth` | ActualCost | TheLastMonth, monthly | `subscriptions/<sub>/actual` | add in config / admin UI |
| `acip-amortized-lastmonth` | AmortizedCost | TheLastMonth, monthly | `subscriptions/<sub>/amortized` | add in config / admin UI |

The default definitions come from `default_exports()` in `app/services/subscription_service.py`
(container `AZURE_COST_EXPORT_CONTAINER`, default `cost-exports`). Each definition is read from
`<root_folder_path>/<export_name>/`.

FOCUS exports are supported by the schema mapper (`dataset_type: focus`; `BilledCost` for actual,
`EffectiveCost` for amortized) but are optional and kept as a separate dataset.

### Supported layouts (`worker/ingestion/discovery.py`)

| Layout | Path | Run unit |
|---|---|---|
| Exports v2 (2023+) | `<root>/<export>/<YYYYMMDD-YYYYMMDD>/<runId>/part_*.csv[.gz]` + `manifest.json` | directory with manifest; period from `runInfo.startDate/endDate`, submission time from `runInfo.submittedTime`; expected row counts from `blobs[].dataRowCount` |
| Legacy | `<root>/<export>/<YYYYMMDD-YYYYMMDD>/<export>_<guid>.csv` | each file; period from the folder name; submission time = blob last-modified |
| Partitioned legacy | `<dir>/_manifest.json` + parts | directory |

Parquet files are reported as unsupported (configure CSV). Gzip CSV is detected by magic bytes.
If a manifest lists files that are not present yet, the run stays `discovered` and is retried later.

### Schema tolerance

Columns are matched case- and punctuation-insensitively against alias lists
(`worker/export_processing/schema.py`): EA/MCA modern (`costInBillingCurrency`), legacy
(`PreTaxCost`), FOCUS (`BilledCost`/`EffectiveCost`, `ChargePeriodStart`, `SubAccountId`).
Unknown columns are preserved in `cost_records.extra`; the original header list and the column
mapping are stored per file (`ingestion_files.source_columns`, `schema_mapping`). Dates accept
`MM/DD/YYYY` (Azure CSV) and ISO formats. Tags accept JSON and the legacy `"k": "v","k2": "v2"`
format. Rows whose `SubscriptionId` does not match the export's subscription are rejected
(`subscription_mismatch`). Exports are expected at **subscription scope**; billing-account-scope
exports containing several subscriptions are not supported.

## Connection tests (Administration → Azure Connections)

`POST /api/v1/azure/connections/test` (all) or `/connections/{subscription_id}/test` runs, per
subscription and independently (`app/services/connection_service.py`):

1. **Authentication** — acquire an ARM token for the collection identity.
2. **Subscription access** — `GET /subscriptions/{id}`.
3. **Cost API access** — a one-day `Microsoft.CostManagement/query` aggregate (validates read
   permission; never used for reporting).
4. **Exports** — list configured exports and flag missing names (warning only).
5. **Storage** — list the first page of blobs under each export definition prefix.

Results are stored on `azure_subscriptions` (`auth_status`, `cost_api_status`, `storage_status`,
`connection_status` = ok / degraded / failed / not_configured / demo, `connection_details` with
remediation hints). A failure in one subscription never stops the others.
`GET /api/v1/azure/subscriptions/discover` lists subscriptions visible to the service principal.

## Local export mode (no storage account yet)

Use this to evaluate real billing data before a storage account and Cost Management exports
exist. Requirements: Azure integration enabled (`AZURE_AUTH_MODE=client_secret` locally) and
**Cost Management Reader** on the subscriptions -- no storage permissions.

```bash
# .env
EXPORT_SOURCE=local
EXPORTS_HOST_PATH=./data/exports      # optional: keep the CSV files on your machine (git-ignored)
```

Then either **Data Management → Pull to local exports** (choose months / cost types /
subscriptions), `POST /api/v1/ingestion/local-export`, or from a terminal:

```bash
docker compose exec backend python -m app.cli export-local --months 3                 # all enabled subscriptions
docker compose exec backend python -m app.cli export-local --months 1 \
    --subscription <subscription-id> --datasets actual                                  # one subscription, actual only
```

For every subscription × calendar month × cost type, the worker calls
`generateCostDetailsReport`, downloads the CSV (Microsoft-managed SAS links) and writes it,
with a `manifest.json`, in exactly the layout an Azure export writes to blob storage:

```
data/exports/cost-exports/subscriptions/<subscription-id>/<actual|amortized>/acip-<dataset>-daily/
    <YYYYMMDD-YYYYMMDD>/<runId>/part_0_0001.csv + manifest.json
```

The files are then ingested by the normal pipeline (row-count completeness check, replace
semantics). Re-pulling a month creates a newer run that **replaces** that month; months for which
Azure reports no data are skipped. Up to 13 months per request; jobs run one at a time (each
report typically takes 30-60 s) and are read-only. The connection test reports Cost Management
exports as "skipped" in this mode because they are not used.

**Moving to the storage account later:** create the Cost Management exports (see
`infrastructure/scripts/create-cost-exports.sh`) using the same container / folder / export
names, grant *Storage Blob Data Reader*, then set `EXPORT_SOURCE=azure_blob` and
`AZURE_STORAGE_ACCOUNT_URL`. Export runs from blob storage are newer and replace the locally
pulled months; no data has to be deleted.

## Cost Details API backfill

`POST /api/v1/ingestion/backfill` (`{subscription_id, metric: ActualCost|AmortizedCost, start_date, end_date}`,
max one month) enqueues a `backfill_cost_details` job. The worker calls
`generateCostDetailsReport` (API 2023-11-01), polls the operation, downloads the SAS-linked CSVs
and ingests them through the same pipeline as a run with `submitted_at = now` (so it replaces the
range). Admin-triggered only; the job queue de-duplicates identical queued/running requests.

## Throttling and retries

`ArmClient.request` retries HTTP 429/5xx up to 3 times, honouring `Retry-After` and the Cost
Management `x-ms-ratelimit-*-retry-after` headers (capped at 60 s). Failed ingestion jobs retry
with exponential backoff (`JOB_RETRY_BACKOFF_SECONDS × 2^(attempt-1)`, `JOB_MAX_ATTEMPTS`).

## Optional evidence sources

- **Activity Log** — `GET /api/v1/resources/{id}/activity` lists write operations on the resource
  for the compared periods (supporting evidence for "what changed", never a conclusion).
- **Azure Advisor** — `app/services/savings_service.import_advisor` imports Cost recommendations
  (job type `advisor_import`, scheduled with the analytics refresh when Azure integration is enabled, or
  on demand via `POST /api/v1/ingestion/advisor`). Requires Reader on each subscription. Demo mode ships
  three clearly-labelled *sample* Advisor items.
- **Resource Graph / Azure Monitor metrics** — not integrated yet; billing quantities are never
  presented as utilisation.

## Local development against real Azure

```bash
cp .env.example .env
# set AZURE_AUTH_MODE=client_secret, AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
#     AZURE_STORAGE_ACCOUNT_URL, and optionally DEMO_MODE=false
cp config/subscriptions.example.json config/subscriptions.json   # edit placeholders
docker compose up --build
```

Then open Administration → Azure Connections → *Test all connections*, and Data Management →
*Synchronize Azure cost data*.
