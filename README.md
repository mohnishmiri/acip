# Azure Cost Intelligence Platform (ACIP)

An enterprise FinOps application that collects Azure billing data from multiple subscriptions,
stores it in PostgreSQL and explains **exactly what changed**: which application, environment,
subscription, Azure service, resource group, resource and billing meter caused a cost increase —
with interactive charts, exact tables, reconciled waterfalls, anomaly detection, budgets,
forecasts and evidence-based savings.

> Runs locally with **`docker compose down -v && docker compose up --build`** and ships with clearly-labelled **DEMO DATA**,
> so no Azure credentials are needed to evaluate it. Production deployment targets AKS
> (Helm chart + Bicep included).

## Modules

| # | Module | Highlights |
|---|---|---|
| 1 | Executive Overview | 12 KPIs (latest day, previous day, current/previous week, current/previous month, YTD, budget, month-end forecast, forecast vs budget, 30-day change, potential savings) with comparisons and significance; trend with previous period, budget pace and forecast; service / application / environment / subscription breakdowns; largest movers; budget consumption |
| 2 | Cost Explorer | 10 visualisations (bar, grouped, stacked, line, area, stacked area, waterfall, donut, treemap, table) from **one** query result; chart / table / split views; 16 group-by dimensions; drill-down with breadcrumb; export |
| 3 | Cost Comparison | Day/week/month/quarter/year/custom, equivalent-elapsed or full calendar comparison, reconciled waterfall, contribution tables, drill-down |
| 4 | Cost Anomalies | 7 transparent rules (relative + absolute significance), severity bands, episode merging, evidence, investigation workflow and notes |
| 5 | Resource Analysis | Server-side paged resource table, resource detail with trends, meters, SKU, tags, anomalies, savings, billing records |
| 6 | Cost Investigation | Meter-level price/volume decomposition; confirmed facts vs labelled hypotheses; optional Activity Log evidence |
| 7 | Application Cost Allocation | Prod / non-prod / total, budget, run rate, forecast, YTD growth, 30-day change; shared and unallocated charges |
| 8 | Production vs Non-Production | Environment comparison, trends, top resources, anomalies, savings |
| 9 | Budget & Forecast | Budgets by scope, thresholds, run-rate / recent / trend forecasts (always labelled as projections) |
| 10 | Potential Cost Savings | Billing-evidence rules + Azure Advisor; estimates never shown as realised savings; read-only |
| 11 | Alerts & Notifications | In-app notifications with de-duplication, configurable rules; Teams / email extension points |
| 12 | Data Management | Freshness, export runs, files (hashes), jobs, errors, sync / retry / reprocess / backfill |
| 13 | Administration & Settings | Subscriptions & exports, Azure connection tests, applications, allocation rules, service categories, anomaly rules, settings, users & roles, audit log |

## Quick start

```bash
docker compose up --build
```

| | |
|---|---|
| Web application | http://localhost:3000 |
| API docs (OpenAPI) | http://localhost:8000/api/docs |
| PostgreSQL | `localhost:5433` (user `acip`, password `acip_local_dev`, database `acip`) |

The first start runs migrations and seeds demo data through the real ingestion pipeline
(≈ 30–60 s). Stop with `docker compose down`; reset all local data with `docker compose down -v`.
More: [docs/local-setup.md](docs/local-setup.md), [docs/docker-deployment.md](docs/docker-deployment.md).

## Demo journey (≈ 5 minutes)

The demo is built so that the **previous week costs exactly $100,000 and the latest week
$110,000 (+$10,000, +10 %)**: AKS +$4,500, Azure SQL +$2,000, Storage +$1,500,
Networking +$1,000, all other services +$1,000. These numbers are computed from ingested billing
records, not hardcoded.

1. **Executive Overview** — the *Current week* KPI shows $110K vs $100K (+10 %). Click it.
2. **Cost Comparison / Cost Explorer** — week-to-date vs previous week, grouped by Azure Service.
   Switch to **Waterfall** (Top 4 + Other): 100,000 → +4,500 → +2,000 → +1,500 → +1,000 →
   Other +1,000 → 110,000, reconciled exactly. Switching chart types keeps every filter.
3. Click **Azure SQL** → the table drills to its resources (breadcrumb *All Applications → Azure SQL*).
4. Click **sqldb-app2-prod-reporting** → Resource Analysis: daily trend, meters, billing records.
5. **Meter-level analysis** — the *General Purpose vCore* meter fell 85 % while the
   *Business Critical vCore* meter started: a tier change (labelled as an unverified hypothesis;
   billing data alone cannot prove a reconfiguration). Compare with
   `aks-userpool-27182818-vmss`: +34.9 % billed hours at an unchanged effective price (pure volume).
6. **Cost Anomalies** — new expensive GPU VM in Non-Production, AKS node-pool spike, weekly
   network egress increase, continuous storage growth — each with evidence and suggested steps.

All demo values are synthetic: the UI shows a *DEMO DATA* banner and exports carry a DEMO marker.

## Architecture

```
Browser ── Next.js (frontend) ──/api proxy──► FastAPI (backend/app) ──► PostgreSQL ◄── worker (backend/worker) ◄── Blob Storage ◄── Cost Management exports
                                                       │                                     │
                                                       └── Azure ARM (connection tests) ◄────┴── existing service principal (secret locally / Workload Identity in AKS)
```

See [docs/architecture.md](docs/architecture.md) for components, data flow and decisions.

## Repository structure

```
backend/                 Python 3.12 — one image for API and worker
  app/                   FastAPI app: api/, core/, models/, schemas/, services/, repositories/,
                         analytics/, anomaly_detection/, forecasting/, integrations/, security/, demo/
  worker/                ingestion/, export_processing/, aggregation/, anomaly_jobs/, scheduled_jobs/
  migrations/            Alembic (source of truth for the schema)
  tests/                 unit/ and integration/ (pytest)
frontend/                Next.js 15 / React 19 / MUI 7 / ECharts / TanStack
  app/  components/  features/  charts/  tables/  services/  hooks/  lib/  styles/
database/                schema/schema.sql (reference dump), seed/ (seeding notes)
infrastructure/
  helm/acip/             Helm chart (dev / staging / prod values)
  kubernetes/            plain manifests rendered from the chart
  bicep/                 Azure resources (ACR, AKS, PostgreSQL, Storage, Key Vault, Log Analytics)
  scripts/               role assignment, Workload Identity federation, export creation, image build
config/                  subscriptions.example.json
docs/                    architecture, database, Azure integration, auth, ingestion, calculations,
                         API reference, local setup, Docker, AKS, security
docker-compose.yml       local stack (+ docker-compose.dev.yml live-reload override)
```

Deviations from the original layout, and why:

- **The worker lives in `backend/worker/` and runs from the backend image** (`python -m worker.main`)
  instead of a top-level `worker/` with its own image. It shares the ORM models, allocation engine,
  aggregation SQL and anomaly engine with the API; one image avoids model drift and doubles
  nothing in build, scan and deploy. It is still a separate process / Deployment.
- **Per-component Dockerfiles** (`backend/Dockerfile`, `frontend/Dockerfile`) instead of a root
  `Dockerfile`: the Python and Node runtimes share nothing and are built and scaled independently.
- `infrastructure/docker/` is unused (Dockerfiles sit next to their code).

## Testing

```bash
docker compose --profile test run --rm tests                   # backend unit + integration (PostgreSQL), coverage
cd frontend && npm run typecheck && npm run lint && npm run build
cd frontend && npx playwright install chromium && npm run test:e2e   # with the stack running
```

The integration suite asserts the mandatory financial validation: $100,000 previous, $110,000
current, +$10,000, +10 %, all five contributors, an exactly reconciled waterfall, and drill-down
to resource billing records; plus idempotent re-ingestion, revised and out-of-order exports,
failure isolation between subscriptions, RBAC and currency separation.

## Configuration

Runtime configuration is environment variables (`.env` locally, ConfigMap/Secret in AKS);
business rules (week start, thresholds, sensitivity, precedence, forecast method) are runtime
settings in Administration → Settings.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | compose: `postgresql+psycopg://acip:acip_local_dev@postgres:5432/acip` | SQLAlchemy URL (secret in AKS) |
| `DEMO_MODE` | `true` | Seed DEMO DATA on first start |
| `APP_ENV`, `LOG_LEVEL`, `LOG_FORMAT` | `local`, `INFO`, `json` (`text` in compose) | Environment and logging |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed browser origins |
| `APP_AUTH_MODE` | `disabled` | `entra` for user sign-in |
| `ENTRA_TENANT_ID`, `ENTRA_API_CLIENT_ID`, `ENTRA_API_AUDIENCE`, `ENTRA_SPA_CLIENT_ID`, `ENTRA_API_SCOPE` | — | User sign-in app registrations |
| `AZURE_AUTH_MODE` | `disabled` | `client_secret` (local), `workload_identity` (AKS), `managed_identity`, `default` |
| `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` | — | Existing collection service principal (secret only for local `client_secret` mode) |
| `AZURE_SUBSCRIPTIONS_CONFIG` | — | Path (e.g. `/config/subscriptions.json`) or inline JSON of applications/subscriptions to register |
| `AZURE_STORAGE_ACCOUNT_URL`, `AZURE_COST_EXPORT_CONTAINER` | —, `cost-exports` | Export storage |
| `EXPORT_SOURCE`, `LOCAL_EXPORT_ROOT` | `auto`, `/data/exports` | `azure_blob` / `local` export source. `local` + Azure integration supports *Pull to local exports* (Cost Details API, no storage account) |
| `EXPORTS_HOST_PATH` | `exports` (Docker volume) | Set to a host path such as `./data/exports` to see the local export CSV files on your machine |
| `EXPORT_DISCOVERY_INTERVAL_MINUTES`, `ANALYTICS_INTERVAL_MINUTES` | `60`, `360` | Worker schedule |
| `WORKER_POLL_INTERVAL_SECONDS`, `JOB_MAX_ATTEMPTS`, `JOB_RETRY_BACKOFF_SECONDS`, `JOB_STALE_AFTER_MINUTES` | `5`, `3`, `60`, `60` | Job queue |
| `INGESTION_REJECT_THRESHOLD_PCT` | `1.0` | Max % rejected rows before a run fails |
| `BACKEND_INTERNAL_URL` (frontend) | `http://backend:8000` | Proxy target for `/api/*` |
| `FRONTEND_HOST_PORT`, `BACKEND_HOST_PORT`, `POSTGRES_HOST_PORT` | `3000`, `8000`, `5433` | Local ports (compose) |

## Documentation

- [Architecture](docs/architecture.md) · [Database design](docs/database-design.md) ·
  [Azure integration](docs/azure-integration.md) · [Authentication](docs/authentication.md)
- [Ingestion design](docs/ingestion-design.md) · [Cost calculations](docs/cost-calculations.md) ·
  [API reference](docs/api-reference.md)
- [Local setup](docs/local-setup.md) · [Docker deployment](docs/docker-deployment.md) ·
  [AKS deployment](docs/aks-deployment.md) · [Security](docs/security.md)
