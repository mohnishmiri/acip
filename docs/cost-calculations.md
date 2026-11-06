# Cost calculations

All formulas live in the backend (`app/analytics`, `app/anomaly_detection`, `app/forecasting`)
and are shared by every endpoint; the frontend never recomputes them. Arithmetic uses
`Decimal`; values are rounded (2 dp money, 4 dp quantity, 6 dp unit price) only when serialised.

## Reporting basis

- **Billing date** = the export's usage `Date`, treated as UTC.
- **Cost type**: `actual` (ActualCost export) or `amortized` (AmortizedCost export). Every query
  is filtered to exactly one; they are never added together.
- **Currency**: every query is filtered to one billing currency. Default = setting
  `reporting.default_currency` when present in scope, otherwise the largest currency. Costs in
  other currencies are reported in `meta.warnings` / `meta.other_currencies`, never summed and
  never converted.

## Periods (`app/analytics/periods.py`)

**As-of date** = latest *complete* usage date in the current scope (override with `as_of`):
`min(latest usage date, today (UTC) − reporting.data_completeness_lag_days)`, default lag 1 day.
Azure keeps adding usage to the current (and sometimes previous) day for hours, so anchoring on
a partial day would read as a cost drop (e.g. a day with $76 of an eventual ~$3,000). Forecasts,
budgets, savings evaluation and anomaly detection use the same anchor; the partial day stays
stored and is replaced by the next export run / pull. The header shows "Data through <complete
day> · <latest day> updating". Set the lag to 0 to anchor on the latest usage date.
Presets are resolved against it: `today`, `yesterday`, `last_7_days`, `last_30_days`,
`last_90_days`, `week_to_date`, `previous_week`, `month_to_date`, `previous_month`,
`quarter_to_date`, `previous_quarter`, `year_to_date`, `previous_year`, `custom`.
Week start is configurable (`reporting.week_start_isodow`, 1 = Monday … 7 = Sunday).
A period whose end is before its nominal end (e.g. week-to-date on Wednesday) is *incomplete*;
the API flags it and reports a run-rate.

**Comparison modes**

| Mode | Definition |
|---|---|
| `previous_equivalent` (default) | Previous unit (day/week/month/quarter/year) covering the **same number of elapsed days** — e.g. 3 days of this week vs the first 3 days of last week; month-to-date on 31 Mar vs 1–28 Feb (clipped to the shorter month). Rolling/custom ranges: the immediately preceding window of equal length. |
| `previous_calendar` | The complete previous calendar unit (whole previous week/month/…). |
| `same_period_last_year` | Same dates one year earlier (29 Feb → 28 Feb). |
| `custom` | Explicit `compare_start_date` / `compare_end_date`. |

If the comparison period starts before the earliest available data, a warning says comparison
values may be understated.

## Comparison metrics (`app/analytics/comparison.py`)

```
difference        = current − previous
percentage change = (current − previous) / |previous| × 100        (null when previous = 0)
share of total    = item current / total current × 100              (null when total = 0)
contribution      = item difference / total difference × 100        (null when total difference = 0)
daily average     = period cost / days in period
run rate          = current daily average × nominal days            (incomplete periods only)
quantity change   = current quantity − previous quantity            (meter grain only; same unit)
```

Using `|previous|` keeps the sign aligned with the direction when the previous value is negative
(net credits). A percentage is never infinite or a divide-by-zero.

**Status** (record presence distinguishes *new* from *rose from zero*):
`new` (no billing records in the comparison period), `removed` (no records in the current period),
`increased`, `decreased`, `unchanged`, `no_data`.

**Significance** (`notable_increase` / `notable_decrease` / `normal`): a movement is *normal
variation* if |difference| < `reporting.significant_change_abs` (default 500) or
|%| < `reporting.significant_change_pct` (default 5). Increases are not automatically "bad".

**Sorting**: default `abs_diff` (largest absolute change — a +500 % change on a $2 resource never
outranks a +$10,000 change); also `pct_increase` (items without a % — new — sort after all items
with one), `largest_increase`, `largest_decrease`, `current_cost`, `previous_cost`,
`contribution`, `name`.

## Waterfall (`build_waterfall`)

```
start = previous total
steps = top-N items by |difference| (non-zero), each step = difference
other = net change − Σ(top-N differences)          (exact residual of all remaining items)
end   = current total
reconciled ⇔ start + Σ steps + other = end         (checked in Decimal; reconciliation_difference reported)
```

`top_n` defaults to `reporting.default_waterfall_top_n` (4). Negative contributions are drawn
as decreases. The chart's value axis does not start at zero (stated under the chart).

## Root-cause decomposition (`app/analytics/decomposition.py`)

Computed at (resource, meter, charge type, pricing model) grain and rolled up; the effects sum
exactly to the total difference (`reconciled`).

| Effect | Formula / rule |
|---|---|
| `volume` | (q₁ − q₀) × p₀, with pᵢ = costᵢ / quantityᵢ (effective price) |
| `price` | difference − volume = (p₁ − p₀) × q₁ |
| `new_meter` / `removed_meter` | whole difference of a meter billed in only one period on an existing resource |
| `new_resource` / `removed_resource` | whole difference of a resource billed in only one period |
| `commitment` | usage that moved between on-demand and reservation / savings plan pricing, and `UnusedReservation` / `UnusedSavingsPlan` charges |
| `credits_refunds` | charge types Refund / Credit / Adjustment or negative non-usage charges |
| `other_charges` | purchases, taxes, rounding and other non-usage charge types |
| `unpriced` | usage rows without quantity |

The response separates **confirmed facts** (measured from billing records: quantities, effective
prices, meters that started/stopped, new/removed resources, charge-type changes) from
**hypotheses** (explicitly labelled possible explanations, e.g. "billed hours rose … consistent
with additional nodes; verify in Activity Log"). Billing data alone never asserts that a
resource was resized or reconfigured.

## Allocation (`app/analytics/allocation.py`)

Each row is assigned exactly once (no double counting). Application and environment are resolved
per dimension by the first source that yields a value, in the order
`attribution.precedence` (default `resource_group_rule → subscription → resource_tag`):

- **resource_group_rule** — `application_mappings` glob on resource group / resource id; a rule may
  mark rows `shared` or `unallocated` (ends the search).
- **subscription** — the subscription's application and environment (primary classification).
- **resource_tag** — `resource_tag_mappings` (`application` / `environment` tags; environment
  aliases such as prod, dev, test, uat, shared).

No match → environment `unallocated`, allocation status `unallocated`; untagged resources are
never silently assigned to Production. Owner, cost center, project, team, business unit and
workload come from tag mappings (cost center falls back to the export's `CostCenter` column).
Service category: first matching `service_category_rules` entry (e.g. `MC_*` resource groups →
Azure Kubernetes Service; meter category Bandwidth → Networking), else *Other Services*.

## Anomaly detection (`app/anomaly_detection`)

Rules combine **relative** (% over baseline) and **absolute** (minimum currency increase)
significance; both must be met. Purchases, refunds, tax and rounding charges are excluded
(`anomaly.exclude_charge_types`). Thresholds are scaled by `anomaly.sensitivity`
(low × 1.5, medium × 1.0, high × 0.67).

Detection is idempotent: a date already covered by *any* episode of the same rule and scope is
skipped, and a detection on the day after an active episode (within 2 days) extends that episode
instead of opening a new one, so one ongoing issue raises one anomaly and one notification.
*New expensive resource* additionally requires `min_prior_history_days` (default 7) of billing
history for the subscription before the resource first appeared -- right after a subscription's
first data load every resource would otherwise look new.

| Rule (seeded) | Scope | Baseline | Default trigger |
|---|---|---|---|
| `DAILY_SERVICE_SPIKE` | subscription × service | median of the same weekday over 4 prior weeks | ≥ 25 % and ≥ 250 (per-category overrides: Networking 20 %/100, Storage 15 %/100, Azure Monitor 25 %/100, Azure SQL 20 %/150, Virtual Machines 20 %/150); ≥ 21 days history |
| `DAILY_RESOURCE_SPIKE` | resource | median of previous 14 days | ≥ 40 % and ≥ 150; ≥ 14 days history |
| `WEEKLY_SERVICE_SPIKE` | subscription × service | mean of previous 4 weekly totals | ≥ 12 % and ≥ 750 |
| `MONTHLY_APPLICATION_SPIKE` | application × environment | same elapsed days of previous month | ≥ 12 % and ≥ 3,000 after ≥ 7 days |
| `NEW_EXPENSIVE_RESOURCE` | resource | none (first billed within 7 days) | average daily cost ≥ 40; severity from projected 30-day cost |
| `NON_PROD_DAILY_SPIKE` | application × Non-Production environment | same weekday median (4 weeks) | ≥ 15 % and ≥ 60 |
| `CONTINUOUS_INCREASE` | resource | first of a 5-week window | 4 consecutive weekly increases each ≥ 3 % and cumulative ≥ 100 |

**Severity** (`anomaly.severity_thresholds`, first band met, checked from critical down):
critical ≥ 5,000 and ≥ 50 %; high ≥ 2,000 and ≥ 30 %; medium ≥ 500 and ≥ 20 %;
low ≥ 100 and ≥ 10 %; otherwise informational (absolute bands scaled by sensitivity; anomalies
without a % — new spend — use absolute bands only).

**Episodes**: a detection for the same rule and scope within 2 days of an *open / investigating /
acknowledged* anomaly extends it (`occurrence_count`, `last_detected_date`, severity may escalate)
instead of creating a new one; re-running over already covered dates is a no-op. Each anomaly
stores evidence (baseline method and points, observed vs baseline, top meters with quantity
changes, top contributing resources, 42-day history) and a factual explanation.

## Forecasts (`app/forecasting/forecast.py`)

For the period (month of the as-of date, or year for annual budgets):

| Method | Projection of each remaining day |
|---|---|
| `run_rate` (default) | actual to date ÷ elapsed days |
| `recent` | average of the last 7 days |
| `trend` | least-squares line over the last 60 days (floored at 0; falls back to run-rate with < 14 days of history) |

`forecast total = actual to date + Σ projected remaining days`. Forecasts are always returned
separately and labelled as projections — never as actual charges.

**Budgets**: utilisation = actual ÷ budget × 100 (null for a zero budget); remaining = budget −
actual; forecast variance = forecast − budget; thresholds crossed (default 70/80/90/100 %) and
*forecast exceeds budget* raise de-duplicated notifications. Annual budgets are pro-rated to
1/12 per month (daily pace = monthly amount ÷ days in month) for trend lines.

## Potential savings (`app/services/savings_service.py`)

Evidence-based rules, never auto-actioned, estimates never labelled as realised:

- **NONPROD_ALWAYS_ON** — Non-Production VM/AKS compute billed ≥ 90 % as many hours on weekends
  as weekdays (14 days) with ≥ `savings.min_monthly_cost` (200) per 30 days; estimate =
  30-day cost × (1 − `savings.nonprod_schedule_hours_per_week` (60) / 168), assumption stated.
- **HIGH_MONITORING_SHARE** — Azure Monitor ≥ 7 % of an application-environment's 30-day cost (not estimated).
- **EGRESS_GROWTH** — Bandwidth cost +≥ 15 % and +≥ 200 vs previous 30 days (not estimated).
- **STEADY_GROWTH** — from open continuous-increase anomalies (not estimated).
- **AZURE_ADVISOR** — imported Advisor cost recommendations (savings as reported by Advisor).

## The mandatory demonstration scenario

Demo data (`app/demo`) is generated so that, across all six demo subscriptions, **actual cost**
of the previous complete week is exactly **100,000.00 USD** and of the latest complete week
**110,000.00 USD** (+10,000.00, +10 %): AKS 30,000 → 34,500; Azure SQL 20,000 → 22,000;
Storage 10,000 → 11,500; Networking 8,000 → 9,000; other services 32,000 → 33,000 (cents
allocated with the largest-remainder method). The numbers are *computed by the reporting layer*
from ingested records — `GET /api/v1/costs/compare?preset=week_to_date&group_by=service_category&top_n=4`
returns a reconciled waterfall `100,000 → +4,500 → +2,000 → +1,500 → +1,000 → Other(6) +1,000 → 110,000`.
The demo as-of date is the last Sunday before the generation date (Monday week start), so
"week-to-date" is the complete scenario week. Integration tests in
`backend/tests/integration/test_demo_scenario.py` assert every figure.
