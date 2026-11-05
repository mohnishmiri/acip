# Database

The **source of truth for the schema is Alembic** in `backend/migrations/` (initial revision
`0001_initial_schema.py`). Migrations run automatically:

- locally — the `init` compose service (`python -m app.cli init`) on every `docker compose up`;
- in AKS — the Helm pre-install / pre-upgrade hook job (`python -m app.cli migrate`).

Run them manually with `docker compose run --rm init python -m app.cli migrate`.

## Contents

| Path | What |
|---|---|
| `schema/schema.sql` | Reference dump of the current schema for review (not applied by anything). Monthly partitions `cost_records_YYYY_MM` are created at runtime and omitted. |
| `seed/README.md` | How reference data and demo data are seeded. |
| `migrations/` | Placeholder — see `backend/migrations/`. |

Regenerate the reference dump after a migration (stack running):

```bash
docker compose exec -T postgres pg_dump --schema-only --no-owner --no-privileges -U acip acip \
  --exclude-table='public.cost_records_2*' > database/schema/schema.sql
```

Design notes: [docs/database-design.md](../docs/database-design.md).
