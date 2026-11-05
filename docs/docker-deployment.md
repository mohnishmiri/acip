# Docker deployment (local / single host)

Files: `docker-compose.yml` (stack), `docker-compose.dev.yml` (live-reload override),
`backend/Dockerfile` (API **and** worker image), `frontend/Dockerfile` (Next.js standalone),
`.env.example`.

## Services

| Service | Image | Purpose | Ports |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | Database (volume `pgdata`) | host `5433` → 5432 |
| `init` | `acip-backend:local` | One-shot `python -m app.cli init`: wait for DB, migrate, seed reference data, register subscriptions, seed demo data (first start, `DEMO_MODE=true`) | — |
| `backend` | `acip-backend:local` | FastAPI (`uvicorn app.main:app`) | host `8000` |
| `worker` | `acip-backend:local` | `python -m worker.main` | — |
| `frontend` | `acip-frontend:local` | Next.js; proxies `/api/*` to `BACKEND_INTERNAL_URL=http://backend:8000` | host `3000` |
| `tests` (profile `test`) | `acip-backend:test` | pytest with coverage against `acip_test` | — |

Volumes: `pgdata` (database), `exports` (local export files: demo data or file-drop exports).
`./config` is mounted read-only at `/config` in the backend containers. Health checks:
backend `/health/ready`, worker heartbeat (`python -m worker.healthcheck`), postgres `pg_isready`,
frontend `/healthz`.

## Commands

```bash
# build and start (foreground)
docker compose up --build
# start in the background / stop / stop and keep data
docker compose up -d --build
docker compose stop
docker compose down
# rebuild one image after code changes
docker compose build backend frontend && docker compose up -d
# logs
docker compose logs -f backend worker
docker compose logs init            # migrations + seeding output
# run database migrations explicitly
docker compose run --rm init python -m app.cli migrate
# (re)initialise demo data: removes existing DEMO subscriptions and data, regenerates and ingests
docker compose run --rm init python -m app.cli seed-demo
# remove demo data only
docker compose run --rm init python -m app.cli reset-demo
# re-run anomaly detection / savings / budget alerts now (optionally wider window)
docker compose exec backend python -m app.cli analytics --lookback-days 60
# test Azure connections from the CLI
docker compose exec backend python -m app.cli test-connections
# reset ALL local data (database and export volume) and start fresh
docker compose down -v && docker compose up --build
# psql
docker compose exec postgres psql -U acip -d acip
# automated tests
docker compose --profile test run --rm tests
# live-reload development (backend/worker source mounted)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## Connecting real Azure data locally

1. `cp .env.example .env` and set:
   `AZURE_AUTH_MODE=client_secret`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`
   (the existing collection service principal), `AZURE_STORAGE_ACCOUNT_URL`,
   `AZURE_COST_EXPORT_CONTAINER`, and `DEMO_MODE=false` if you do not want demo data.
2. `cp config/subscriptions.example.json config/subscriptions.json`, replace placeholders, keep
   `AZURE_SUBSCRIPTIONS_CONFIG=/config/subscriptions.json` (or register subscriptions in
   Administration → Subscriptions instead and leave the variable empty).
3. `docker compose up --build` (or `docker compose run --rm init` again to load new config).
4. Administration → Azure Connections → *Test all connections*; then Data Management →
   *Synchronize Azure cost data*.

`.env` and `config/subscriptions.json` are git-ignored. Secrets are passed only as environment
variables at runtime and are never baked into images.

## File-drop exports (no Azure access)

With `EXPORT_SOURCE=local`, export definitions read
`$LOCAL_EXPORT_ROOT/<container>/<root_folder_path>/<export_name>/…` from the `exports` volume
(same v2 layout as Blob Storage), which is useful for testing downloaded export files.

## Images

- `backend/Dockerfile`: `python:3.12-slim`, non-root uid 10001, `curl` + `postgresql-client`,
  `INSTALL_DEV=true` build arg adds test tooling. The same image runs the API (default `CMD`),
  the worker (`python -m worker.main`) and jobs (`python -m app.cli …`).
- `frontend/Dockerfile`: multi-stage Node 22 Alpine build, Next.js `output: "standalone"`,
  non-root uid 10001, `BACKEND_INTERNAL_URL` read at runtime.

Per-component Dockerfiles are used instead of one root Dockerfile because the two runtimes
(Python, Node) share nothing and are built, scanned and scaled independently.
