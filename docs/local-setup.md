# Local setup

## Prerequisites

- Docker Desktop (or Docker Engine) with Compose v2 — the only hard requirement.
- Optional for working outside containers: Node.js 22+ and npm (frontend), Python 3.12 (backend).

No Azure credentials are needed: by default `DEMO_MODE=true` and `AZURE_AUTH_MODE=disabled`, and
the first start seeds clearly-labelled **DEMO DATA** through the real ingestion pipeline.

## Start

```bash
git clone <repo> && cd cost-explorer
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:3000 | Web application |
| http://localhost:8000/api/docs | API (OpenAPI / Swagger UI) |
| localhost:5433 | PostgreSQL (`acip` / `acip_local_dev`, database `acip`) — host port 5433 to avoid clashing with a local 5432 |

Start-up order: `postgres` → `init` (migrations, reference data, subscriptions from
`AZURE_SUBSCRIPTIONS_CONFIG`, demo seeding on first start; about 30–60 s) → `backend` + `worker`
→ `frontend`. Ports can be changed with `FRONTEND_HOST_PORT`, `BACKEND_HOST_PORT`,
`POSTGRES_HOST_PORT` in `.env`.

## Configuration

Copy `.env.example` to `.env` (git-ignored) and edit. Important: `.env.example` sets
`AZURE_SUBSCRIPTIONS_CONFIG=/config/subscriptions.json`. To register subscriptions from a file,
create it (`cp config/subscriptions.example.json config/subscriptions.json` and replace the
placeholders); if the file does not exist, `init` logs a warning and skips it (subscriptions can
also be registered in Administration → Subscriptions). `./config` is mounted read-only at `/config`.

> Docker Compose also reads variables from your **shell**. If your shell already exports
> `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` (common for Azure CLI / Terraform
> users), they are passed into the containers. They stay inert until you set
> `AZURE_AUTH_MODE=client_secret`; the secret is never returned by the API.

## Working on the code

Live-reload backend and worker (source mounted, `uvicorn --reload`):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Frontend with hot reload against the containerised API:

```bash
cd frontend
npm ci
BACKEND_INTERNAL_URL=http://localhost:8000 npm run dev      # http://localhost:3000 (stop the frontend container first)
npm run typecheck && npm run lint
```

## Tests

```bash
docker compose --profile test run --rm tests                 # backend unit + integration tests with coverage
cd frontend && npx playwright install chromium && npm run test:e2e   # end-to-end (needs the stack running)
```

Integration tests create and drop a separate `acip_test` database on the compose PostgreSQL and
load the demo scenario with a fixed date, then assert the mandatory financial figures.

## Simulating roles locally

With `APP_AUTH_MODE=disabled`, use the user menu → *Simulate role* in the UI, or send
`X-ACIP-Dev-Role: viewer` (and optionally `X-ACIP-Dev-Application: <id>`) to the API.

More commands: `docs/docker-deployment.md`.

## Troubleshooting

### `password authentication failed for user "acip"` (init keeps waiting / exits)

PostgreSQL stores the user's password only when the `pgdata` volume is **first** created. If
`POSTGRES_PASSWORD` (or `POSTGRES_USER` / `POSTGRES_DB`) changed afterwards -- typically by
creating `.env` from `.env.example` after an earlier start -- the services connect with credentials
the existing database does not accept. `init` detects this and exits with instructions.

Keep the data and align the stored password with the value now in `.env`:

```bash
docker compose up -d postgres
docker compose exec -T postgres sh -c 'echo "ALTER USER $POSTGRES_USER WITH PASSWORD :'"'"'pw'"'"';" | psql -U "$POSTGRES_USER" -d postgres -v pw="$POSTGRES_PASSWORD"'
docker compose up --build
```

Or start fresh (demo data is regenerated automatically in about a minute):

```bash
docker compose down -v && docker compose up --build
```

