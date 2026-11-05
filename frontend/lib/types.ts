export interface PeriodOut {
  start: string;
  end: string;
  days: number;
  label: string;
  description: string;
  preset?: string;
  unit?: string;
  nominal_start?: string;
  nominal_end?: string;
  is_incomplete?: boolean;
}

export interface ReportMeta {
  as_of: string;
  data_start: string | null;
  data_end: string | null;
  period: PeriodOut;
  comparison_period: PeriodOut | null;
  comparison_mode: string;
  currency: string;
  cost_type: string;
  granularity: string;
  is_demo: boolean;
  warnings: string[];
  other_currencies: { currency: string; total: number }[];
  page?: number;
  page_size?: number;
  total?: number;
  totals?: Totals;
  [k: string]: unknown;
}

export interface Envelope<T> {
  data: T;
  meta: ReportMeta;
}

export interface Totals {
  current: number;
  previous: number | null;
  diff: number | null;
  pct: number | null;
  status: string | null;
  current_daily_avg: number | null;
  previous_daily_avg: number | null;
  run_rate: number | null;
  significance: "normal" | "notable_increase" | "notable_decrease" | null;
}

export interface GroupItem {
  key: string;
  label: string;
  current: number;
  previous?: number;
  diff?: number;
  pct?: number | null;
  status?: string;
  share_of_total?: number | null;
  contribution_pct?: number | null;
  current_records?: number;
  previous_records?: number;
  current_daily_avg?: number | null;
  previous_daily_avg?: number | null;
  current_quantity?: number | null;
  previous_quantity?: number | null;
  quantity_diff?: number | null;
  unit?: string | null;
  attributes?: Record<string, unknown>;
}

export interface Series {
  granularity: string;
  buckets: string[];
  coverage?: [number, number][]; // [days of bucket inside the period, days in bucket]
  series: { key: string; label: string; values: number[] }[];
  total: number[];
  previous_total: (number | null)[] | null;
  previous_buckets: (string | null)[] | null;
}

export interface WaterfallStep {
  key: string;
  label: string;
  kind: "start" | "increase" | "decrease" | "end" | "other";
  value: number;
  start: number;
  end: number;
  previous: number | null;
  current: number | null;
  pct: number | null;
  status: string | null;
  member_count: number | null;
}

export interface Waterfall {
  previous_total: number;
  current_total: number;
  net_change: number;
  pct_change: number | null;
  reconciled: boolean;
  reconciliation_difference: number;
  top_n: number;
  other_member_count: number;
  steps: WaterfallStep[];
}

export interface ExplorerData {
  group_by: string;
  group_by_label: string;
  next_level: string | null;
  filter_param: string | null;
  totals: Totals;
  groups: GroupItem[];
  group_count: number;
  groups_truncated: boolean;
  series: Series;
  waterfall: Waterfall | null;
}

export interface Kpi {
  key: string;
  title: string;
  kind: "actual" | "budget" | "forecast" | "estimate";
  current: number | null;
  previous: number | null;
  diff: number | null;
  pct: number | null;
  period: PeriodOut | null;
  comparison_period: PeriodOut | null;
  significance: string | null;
  sparkline: "daily" | "weekly" | "monthly" | null;
  link: Record<string, string>;
  note: string | null;
  display?: string;
}

export interface FilterOptions {
  applications: { id: number; code: string; name: string; is_demo: boolean; has_subscriptions: boolean }[];
  environments: { code: string; name: string; group: string; is_production: boolean }[];
  environment_groups: { code: string; name: string }[];
  subscriptions: { subscription_id: string; subscription_name: string; application_id: number | null; environment: string | null; billing_currency: string; enabled: boolean; is_demo: boolean }[];
  service_categories: string[];
  regions: string[];
  currencies: string[];
  charge_types: string[];
  pricing_models: string[];
  owners: string[];
  cost_centers: string[];
  resource_groups: string[];
  resource_types: string[];
  meter_categories: string[];
  tag_keys: string[];
  presets: { value: string; label: string }[];
  comparison_modes: { value: string; label: string }[];
  group_by: { value: string; label: string }[];
  week_start_isodow: number;
  default_currency: string;
  default_waterfall_top_n: number;
}

export interface Freshness {
  status: string;
  status_label: string;
  latest_usage_date: string | null;
  oldest_latest_usage_date: string | null;
  last_successful_ingestion: string | null;
  last_ingestion_attempt: string | null;
  subscriptions_with_data: number;
  subscriptions_enabled: number;
  is_demo: boolean;
  current_period_note: string;
  subscriptions: {
    subscription_id: string;
    subscription_name: string;
    enabled: boolean;
    is_demo: boolean;
    status: string;
    latest_usage_date: { actual: string | null; amortized: string | null };
    earliest_usage_date: { actual: string | null };
    last_successful_sync_at: string | null;
    last_sync_attempt_at: string | null;
    last_sync_error: string | null;
    data_lag_hours: number | null;
  }[];
}

export interface Me {
  name: string;
  email: string | null;
  roles: string[];
  primary_role: string | null;
  permissions: string[];
  auth_mode: string;
  scoped_application_ids: number[] | null;
}
