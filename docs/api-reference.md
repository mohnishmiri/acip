# API reference

Base path `/api/v1`. Interactive OpenAPI documentation: **`/api/docs`** (Swagger UI),
`/api/redoc`, schema at `/api/openapi.json` (locally http://localhost:8000/api/docs).

## Conventions

- **Auth**: `Authorization: Bearer <Entra access token>` when `APP_AUTH_MODE=entra`. Permissions per
  endpoint: `read`, `export`, `manage_budgets`, `manage_anomalies`, `manage_savings`, `manage_alerts`,
  `ingestion`, `admin` (see `docs/authentication.md`).
- **Envelope** for reporting endpoints: `{ "data": …, "meta": { … } }`. `meta` always contains
  `as_of`, `data_start`, `data_end`, `period` (start, end, days, label, preset, nominal_end,
  is_incomplete), `comparison_period`, `comparison_mode`, `currency`, `cost_type`, `granularity`,
  `week_start_isodow`, `is_demo`, `warnings[]`, `other_currencies[]`, `generated_at`, and paging
  (`page`, `page_size`, `total`) where relevant.
- **Errors**: `{ "error": { "code", "message", "details", "request_id" } }` with 401, 403, 404, 409,
  422 (validation) or 500/502. Every response carries `X-Request-ID`.
- **Pagination**: `page` (1-based), `page_size` (≤ 1000). Sorting is server-side.

### Common reporting parameters

| Parameter | Values |
|---|---|
| `preset` | `today`, `yesterday`, `last_7_days`, `last_30_days` (default), `last_90_days`, `week_to_date`, `previous_week`, `month_to_date`, `previous_month`, `quarter_to_date`, `previous_quarter`, `year_to_date`, `previous_year`, `custom` (+ `start_date`, `end_date`) |
| `comparison` | `previous_equivalent` (default), `previous_calendar`, `same_period_last_year`, `custom` (+ `compare_start_date`, `compare_end_date`), `none` |
| `granularity` | `daily`, `weekly`, `monthly` |
| `cost_type` | `actual` (default), `amortized` |
| `currency` | ISO code (default: setting or dominant currency in scope) |
| `as_of` | override the latest-data anchor date |
| `group_by` | `application`, `environment`, `subscription`, `service_category`, `resource_group`, `resource`, `resource_type`, `meter_category`, `meter_name`, `region`, `sku`, `cost_center`, `owner`, `charge_type`, `pricing_model`, `tag` (+ `tag_key`) |
| Filters (repeatable) | `application` (id, `shared`, `unallocated`), `environment` (`production`, `non_production`, `shared`, `unallocated`, `development`, `testing`, `uat`), `subscription` (GUID), `service_category`, `region`, `resource_group`, `resource` (ARM id), `resource_type`, `owner`, `cost_center`, `meter_category`, `meter_name`, `sku`, `charge_type`, `pricing_model`, `tag` (`key=value`; value `__none__` = untagged), `search` |
| `top_n` | waterfall contributors before "Other" (1–50; default setting `reporting.default_waterfall_top_n`) |
| `sort` | `abs_diff` (default), `pct_increase`, `largest_increase`, `largest_decrease`, `current_cost`, `previous_cost`, `contribution`, `name` |

## Metadata

| Method & path | Description |
|---|---|
| `GET /meta/client-config` | Public SPA runtime config (auth mode, Entra SPA client id / authority / scope, demo flag). |
| `GET /meta/me` | Current user, roles, permissions, application scope. |
| `GET /meta/filters` | Applications, environments, subscriptions, service categories, regions, currencies, tag keys, presets, comparison modes, group-by options, defaults. |
| `GET /meta/freshness` | Overall and per-subscription data freshness. |

## Executive Overview

| Method & path | Description |
|---|---|
| `GET /dashboard/overview` | 12 KPIs (latest day, previous day, current week, previous week, current month, previous month, YTD, monthly budget, month-end forecast, forecast vs budget, 30-day change, potential savings) with comparisons, significance and sparklines (daily 30d, weekly 12w, monthly 13m). |
| `GET /dashboard/trends` | Series with previous-period overlay, budget line and forecast projection. |
| `GET /dashboard/{service,application,environment,subscription}-breakdown` | Grouped comparison for one dimension. |

## Cost Explorer & Comparison

| Method & path | Description |
|---|---|
| `GET /costs/explorer` | One result for every chart type and the table: `totals`, `groups` (≤ 500 + Other), `series` (≤ 8 named series + Other; `coverage` = [days inside period, days in bucket] so partial weeks/months are marked), `waterfall`, `next_level`, `filter_param`. `group_by=meter` groups by meter tier + name (e.g. GP vs Business Critical vCore) and is display-only. |
| `GET /costs/compare` | Comparison with reconciled `waterfall`, ranked `groups`, `summary` (increased/decreased/new/removed counts, gross increase/decrease). Requires a comparison. |
| `GET /costs/trend` | Series only. |
| `GET /costs/grouped` | Grouped costs, paged (sorted by current cost by default). |
| `GET /costs/contributors` | Paged comparison rows (default `group_by` as given, sort `abs_diff`); resource rows include attributes. |
| `GET /costs/meter-comparison` | Meter-level decomposition for any filter scope (`effects`, `meters`, `resources`, `confirmed_facts`, `hypotheses`, `reconciled`). |
| `GET /costs/records` | Raw billing records behind the view (paged; `include_comparison=true` adds the comparison period). |
| `GET|POST /costs/saved-comparisons`, `DELETE /costs/saved-comparisons/{id}` | Saved comparison views (stores parameters; owner or admin can delete). |
| `GET /costs/export` | File download: `view` = `explorer` \| `compare` \| `contributors` \| `resources` \| `records`, `format` = `csv` \| `xlsx`. The file starts with context rows (period, comparison, currency, cost type, filters, as-of, DEMO marker). |

Example:

```bash
curl -s "http://localhost:8000/api/v1/costs/compare?preset=week_to_date&group_by=service_category&top_n=4" | jq '.data.waterfall.steps[] | {label, value}'
```

## Resource Analysis

| Method & path | Description |
|---|---|
| `GET /resources` | Resources with comparison, attributes, primary meter, tags (server-side paged; `sort`, `sort_dir`, `search`). |
| `GET /resources/{id}` | Resource details, totals, meters, anomaly counts, savings. |
| `GET /resources/{id}/history` | Daily cost (90 d), monthly cost (13 m), top meters' daily cost and quantity. |
| `GET /resources/{id}/meters` | Meter-level root-cause decomposition. |
| `GET /resources/{id}/records` | Billing records (current + comparison period). |
| `GET /resources/{id}/anomalies` | Anomaly history. |
| `GET /resources/{id}/activity` | Optional Azure Activity Log events (unavailable in demo mode). |

`{id}` is the internal `azure_resources.id`; look it up with `GET /resources?resource=<ARM id>`.

## Cost Anomalies

| Method & path | Description |
|---|---|
| `GET /anomalies` | Filters `status`, `severity`, `rule_code`, `category`, `application`, `environment`, `subscription`, `date_from`, `date_to`, `search`; `sort` = `severity` \| `detection_date` \| `absolute_increase` \| `percentage_increase`; `meta.open_by_severity`. |
| `GET /anomalies/rules` / `PUT /anomalies/rules/{id}` | List / update detection rules (thresholds, filters, enabled). |
| `GET /anomalies/{id}` | Anomaly with evidence, explanation, recommended steps, events. |
| `POST /anomalies/{id}/status` | `{status: open\|investigating\|acknowledged\|resolved\|dismissed\|expected, comment?}` |
| `POST /anomalies/{id}/comments` | `{comment}` |

## Application Cost Allocation

| Method & path | Description |
|---|---|
| `GET /applications` | Per application (+ Shared Services, Unallocated): production / non-production / total, previous, budget, month-to-date, run rate, forecast, expected variance, YTD and growth, 30-day change, potential savings, open anomalies. |
| `GET /applications/{id}` | Subscriptions, breakdowns by environment / subscription / service / resource group, top resources and movers, budget status, anomalies, savings. |
| `GET /applications/{id}/costs` | Explorer result scoped to the application. |

## Budget & Forecast

| Method & path | Description |
|---|---|
| `GET /budgets` | Budgets with actual, utilisation, remaining, forecast, variance, daily run rate, thresholds crossed. |
| `POST /budgets`, `PUT /budgets/{id}`, `DELETE /budgets/{id}` | Body: `name, scope_type (total\|application\|subscription\|environment\|resource_group), scope_ref, period_type (monthly\|annual), amount, currency, cost_type, start_date, end_date?, thresholds[], forecast_alert, enabled, notes`. |
| `GET /forecasts` | Month-end forecast for the current filters with all three methods, actual series, annual projection, matching budget. `method` optional. |

## Potential Cost Savings

`GET /savings` (filters `status`, `source`, `application`, `environment`), `GET /savings/summary`,
`POST /savings/{id}/status` (`open`, `investigating`, `accepted`, `dismissed`, `implemented`).

## Alerts & Notifications

`GET /notifications` (`unread_only`, `notification_type`, paging), `POST /notifications/read`
(`{ids?}`; all when omitted), `GET|POST /alert-rules`, `PUT|DELETE /alert-rules/{id}`
(alert types: `anomaly`, `budget_threshold`, `budget_forecast`, `ingestion_failure`,
`data_delay`, `savings_opportunity`; channels `in_app` — `teams` / `email` are extension points).

## Data Management & Ingestion

| Method & path | Description |
|---|---|
| `GET /ingestion/status` | Freshness + active jobs. |
| `GET /ingestion/jobs`, `GET /ingestion/jobs/{id}` | Job history; detail includes errors and audit log lines. |
| `POST /ingestion/trigger` | `{subscription_ids?, force?, period_from?, period_to?, dataset_types?}` → one `sync_subscription` job per subscription (existing queued/running jobs are reused). |
| `POST /ingestion/retry/{id}` | Retry a failed job. |
| `POST /ingestion/reprocess` | `{subscription_id, period_from, period_to, dataset_types?}` (forced re-ingestion). |
| `POST /ingestion/backfill` | `{subscription_id, metric, start_date, end_date}` via the Cost Details API (≤ 1 month). |
| `POST /ingestion/analytics?lookback_days=3` | Re-run analytics. |
| `POST /ingestion/local-export` | `{subscription_ids?, months?=3, start_date?, end_date?, dataset_types?}` — local export mode: Cost Details API → local export folder (Azure layout) → ingestion; one job per subscription. Requires `EXPORT_SOURCE=local` and Azure integration. |
| `POST /ingestion/advisor` | Import Azure Advisor cost recommendations (job; requires Azure integration). |
| `GET /ingestion/runs`, `/files`, `/errors`, `/audit` | Export run registry, source files (hashes, row counts, schema), data-quality errors, audit log. |

## Azure Connections

`GET /azure/connections`, `POST /azure/connections/test` (`{subscription_ids?}`),
`POST /azure/connections/{subscription_id}/test`, `GET /azure/subscriptions/discover`.

## Administration & Settings

| Method & path | Description |
|---|---|
| `GET|POST /admin/subscriptions`, `PUT|DELETE /admin/subscriptions/{subscription_id}` | Register / update / delete subscriptions and their export definitions (delete refused once data exists — disable instead). |
| `GET|POST /admin/applications`, `PUT|DELETE /admin/applications/{id}` | Applications (delete refused while subscriptions, budgets or billing history reference it — set inactive instead). |
| `GET|POST /admin/tag-mappings`, `PUT|DELETE /admin/tag-mappings/{id}` | Tag → dimension mappings. |
| `GET|POST /admin/application-mappings`, `PUT|DELETE …/{id}` | Resource-group / resource rules (shared, unallocated, overrides). |
| `GET|POST /admin/category-rules`, `PUT|DELETE …/{id}` | Service category rules. |
| `POST /admin/reattribute?subscription_id=` | Re-apply rules to stored records (job). |
| `GET /admin/settings`, `PUT /admin/settings/{key}` | Runtime settings (`{value}`), validated per key. |
| `GET /admin/roles`, `GET /admin/users`, `POST /admin/role-assignments`, `DELETE /admin/role-assignments/{id}` | RBAC. |
| `GET /admin/audit-logs` | Audit trail. |

## Health

`GET /health/live` (process), `GET /health/ready` (database reachable and migrated; returns schema revision).
