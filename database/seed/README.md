# Seeding

All seeding is idempotent and performed by `python -m app.cli init` (compose `init` service,
Helm post-install/post-upgrade `acip-init` job).

## Reference data (always) — `backend/app/services/seed_service.py`

- `environments`: production, non_production, development, testing, uat, shared, unallocated
  (with environment groups used by the global filter)
- `roles`: administrator, finops_analyst, engineering_lead, viewer (mapped to Entra app roles
  `ACIP.Administrator`, `ACIP.FinOpsAnalyst`, `ACIP.EngineeringLead`, `ACIP.Viewer`)
- `service_category_rules`: default classification (AKS node resource groups `MC_*`, VMs, SQL,
  Storage, Networking, Azure Monitor, App Service, Key Vault, Container Registry, …)
- `resource_tag_mappings`: owner, cost center, project, team, business unit, workload,
  application, environment tag keys
- `anomaly_rules`: 7 transparent detection rules
- `alert_rules`: anomaly (medium+), budget threshold, forecast over budget, ingestion failure,
  data delay, savings opportunity (> 500/month)

Runtime settings have code defaults (`backend/app/services/settings_service.py`); only changed
values are stored in `application_settings`.

## Subscriptions (optional)

`AZURE_SUBSCRIPTIONS_CONFIG` → applications and subscriptions with export definitions, see
`config/subscriptions.example.json`. Subscriptions can also be managed in Administration.

## DEMO DATA (only when `DEMO_MODE=true` and no demo subscriptions exist)

`backend/app/demo/` registers three applications and six `DEMO-…` subscriptions, generates
synthetic Cost Management export files (ActualCost + AmortizedCost, Jan of last year → the last
complete week, including a revised month-to-date run, a reservation purchase and a refund) into
`$LOCAL_EXPORT_ROOT/cost-exports/demo/`, ingests them through the production pipeline, creates
demo budgets and three sample "Advisor-style" recommendations, and runs analytics. Everything is
flagged `is_demo` and labelled DEMO DATA in the UI.

```bash
docker compose run --rm init python -m app.cli seed-demo     # regenerate
docker compose run --rm init python -m app.cli reset-demo    # remove
```
