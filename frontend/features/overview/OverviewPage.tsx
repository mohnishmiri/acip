"use client";
import { Box, Grid, LinearProgress, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";
import EChart, { type EChartsOption } from "@/charts/EChart";
import { barOption, donutOption, trendOption } from "@/charts/options";
import { DeltaText, MoneyText } from "@/components/common/Delta";
import { KpiCard } from "@/components/common/KpiCard";
import { PageHeader } from "@/components/common/PageHeader";
import { Section } from "@/components/common/Section";
import { ChartSkeleton, EmptyState, ErrorState, Warnings } from "@/components/common/States";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { useUrlState } from "@/hooks/useUrlState";
import { bucketLabel, compactMoney, escapeHtml, money, pct, periodText } from "@/lib/format";
import type { Envelope, GroupItem, Kpi, Series, Totals } from "@/lib/types";
import { useApi, useOverview } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { comparisonColumns } from "@/tables/columns";
import { fontStack, ink, polarity, surface } from "@/styles/tokens";

type Breakdown = Envelope<{ group_by: string; totals: Totals; groups: GroupItem[] }>;
type TrendData = Envelope<Series & { budget: (number | null)[] | null; budget_name: string | null; forecast: { points: { date: string; value: number }[]; method_label: string; forecast_total: number } | null }>;
interface BudgetRow {
  id: number;
  name: string;
  scope_label: string;
  amount: number;
  actual: number;
  utilization_pct: number | null;
  forecast: number;
  forecast_utilization_pct: number | null;
  remaining: number;
  currency: string;
  period_type: string;
  forecast_exceeds_budget: boolean;
}

const KPI_LINKS: Record<string, (l: (p: string, e?: Record<string, string>) => string) => string> = {
  today: (l) => l("/explorer", { preset: "today", cmp: "previous_equivalent" }),
  yesterday: (l) => l("/explorer", { preset: "yesterday" }),
  current_week: (l) => l("/comparison", { preset: "week_to_date" }),
  previous_week: (l) => l("/comparison", { preset: "previous_week" }),
  current_month: (l) => l("/explorer", { preset: "month_to_date" }),
  previous_month: (l) => l("/explorer", { preset: "previous_month", gran: "daily" }),
  year_to_date: (l) => l("/explorer", { preset: "year_to_date", gran: "monthly", cmp: "same_period_last_year", chart: "line" }),
  budget: (l) => l("/budgets"),
  forecast: (l) => l("/budgets"),
  budget_variance: (l) => l("/budgets"),
  change_30d: (l) => l("/explorer", { preset: "last_30_days" }),
  savings: (l) => l("/savings"),
};

function divergingOption(items: GroupItem[], currency: string): EChartsOption {
  const rows = [...items].reverse();
  return {
    textStyle: { fontFamily: fontStack },
    grid: { left: 20, right: 56, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(15,108,189,0.06)" } },
      backgroundColor: "#fff",
      borderColor: surface.border,
      textStyle: { color: ink.primary, fontSize: 12 },
      formatter: (ps: { dataIndex: number }[]) => {
        const g = rows[ps[0].dataIndex];
        return `<b>${escapeHtml(g.label)}</b><br/>Change: <b>${money(g.diff ?? 0, currency, { sign: true })}</b><br/>Previous: ${money(g.previous ?? 0, currency)}<br/>Current: ${money(g.current, currency)}${g.status === "new" ? "<br/><i>New in this period</i>" : ""}`;
      },
    },
    xAxis: { type: "value", axisLabel: { color: ink.axis, fontSize: 11, formatter: (v: number) => compactMoney(v, currency) }, splitLine: { lineStyle: { color: ink.grid } } },
    yAxis: { type: "category", data: rows.map((r) => r.label), axisLabel: { color: ink.secondary, fontSize: 11, width: 150, overflow: "truncate" }, axisTick: { show: false }, axisLine: { lineStyle: { color: ink.baseline } } },
    series: [
      {
        type: "bar",
        barMaxWidth: 16,
        data: rows.map((r) => ({ value: r.diff ?? 0, itemStyle: { color: (r.diff ?? 0) >= 0 ? polarity.increase : polarity.decrease, borderRadius: (r.diff ?? 0) >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4] } })),
        label: { show: true, position: "right", color: ink.secondary, fontSize: 11, formatter: (p: { value: number }) => `${p.value >= 0 ? "+" : ""}${compactMoney(p.value, currency)}` },
      },
    ],
  };
}

function BreakdownCard({ dim, title, chart, params, labelHeader, onPick, height = 280 }: { dim: string; title: string; chart: "bar" | "grouped" | "donut"; params: Record<string, unknown>; labelHeader: string; onPick?: (g: GroupItem) => void; height?: number }) {
  const path = { service_category: "/dashboard/service-breakdown", application: "/dashboard/application-breakdown", environment: "/dashboard/environment-breakdown", subscription: "/dashboard/subscription-breakdown" }[dim]!;
  const q = useApi<Breakdown>(path, params as never);
  const d = q.data;
  const currency = d?.meta.currency ?? "USD";
  const hasCmp = !!d?.meta.comparison_period;
  const option = useMemo(() => {
    if (!d) return null;
    if (chart === "donut") return donutOption(d.data.groups, { currency, dimension: dim });
    return barOption(d.data.groups, { currency, grouped: chart === "grouped", hasComparison: hasCmp, max: 12 });
  }, [d, chart, currency, dim, hasCmp]);
  const cols = useMemo(() => comparisonColumns({ currency, hasComparison: hasCmp, labelHeader, onLabelClick: onPick }), [currency, hasCmp, labelHeader, onPick]);
  return (
    <Section
      title={title}
      subtitle={d ? `${periodText(d.meta.period)}${hasCmp ? ` vs ${periodText(d.meta.comparison_period)}` : ""} · ${currency} · ${d.meta.cost_type}` : " "}
      testId={`breakdown-${dim}`}
      table={d ? <DataTable data={d.data.groups} columns={cols} maxHeight={height + 40} defaultHidden={["previous_daily_avg", "current_records", "current_daily_avg", "contribution_pct"]} storageKey={`overview-${dim}`} onRowClick={onPick} /> : undefined}
    >
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !option ? <ChartSkeleton height={height} /> : d!.data.groups.length === 0 ? <EmptyState message="No cost in this period." /> : (
        <EChart option={option} height={height} ariaLabel={`${title} chart`} onClick={onPick ? (p) => { const g = d!.data.groups.find((x) => x.label === p.name); if (g) onPick(g); } : undefined} />
      )}
    </Section>
  );
}

export default function OverviewPage() {
  const { apiParams } = useGlobalFilters();
  const link = useLinkWithFilters();
  const router = useRouter();
  const [local, setLocal] = useUrlState({ gran: "daily" });
  const overview = useOverview({ ...apiParams, preset: undefined, start_date: undefined, end_date: undefined });
  const trend = useApi<TrendData>("/dashboard/trends", { ...apiParams, granularity: local.gran });
  const movers = useApi<Envelope<GroupItem[]>>("/costs/contributors", { ...apiParams, group_by: "resource", sort: "abs_diff", page_size: 10 });
  const serviceMovers = useApi<Envelope<{ waterfall: unknown; groups: GroupItem[] }>>("/costs/compare", { ...apiParams, group_by: "service_category" });
  const budgets = useApi<{ data: BudgetRow[] }>("/budgets");

  const currency = overview.data?.meta.currency ?? trend.data?.meta.currency ?? "USD";
  const kpis = overview.data?.data.kpis ?? [];
  const spark = overview.data?.data.sparklines;
  const trendOpt = useMemo(() => (trend.data ? trendOption(trend.data.data, trend.data.meta.currency) : null), [trend.data]);
  const moverOpt = useMemo(() => (movers.data ? divergingOption(movers.data.data, movers.data.meta.currency) : null), [movers.data]);
  const serviceMoverRows = useMemo(() => [...(serviceMovers.data?.data.groups ?? [])].filter((g) => (g.diff ?? 0) !== 0).slice(0, 8), [serviceMovers.data]);
  const serviceMoverOpt = useMemo(() => (serviceMovers.data ? divergingOption(serviceMoverRows, serviceMovers.data.meta.currency) : null), [serviceMovers.data, serviceMoverRows]);

  const trendColumns = useMemo<ColumnDef<{ bucket: string; current: number; previous: number | null; budget: number | null }, unknown>[]>(
    () => [
      { accessorKey: "bucket", header: "Period", size: 140, cell: ({ getValue }) => bucketLabel(getValue() as string, local.gran) },
      { accessorKey: "current", header: "Actual", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} bold /> },
      { accessorKey: "previous", header: "Previous period", size: 140, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number | null} currency={currency} /> },
      { id: "diff", header: "Difference", size: 130, meta: { numeric: true }, accessorFn: (r) => (r.previous === null ? null : r.current - r.previous), cell: ({ getValue }) => <DeltaText value={getValue() as number | null} currency={currency} /> },
      { accessorKey: "budget", header: "Budget pace", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number | null} currency={currency} /> },
    ],
    [currency, local.gran],
  );
  const trendRows = useMemo(
    () => (trend.data ? trend.data.data.buckets.map((b, i) => ({ bucket: b, current: trend.data!.data.total[i], previous: trend.data!.data.previous_total?.[i] ?? null, budget: trend.data!.data.budget?.[i] ?? null })) : []),
    [trend.data],
  );
  const moverCols = useMemo(() => comparisonColumns({ currency, hasComparison: true, labelHeader: "Resource" }), [currency]);
  const pick = (dim: string) => (g: GroupItem) =>
    router.push(link("/explorer", { drill: JSON.stringify([{ dim, key: g.key, label: g.label }]), group: dim === "service_category" ? "resource" : "service_category", chart: "bar" }));

  return (
    <Box>
      <PageHeader
        title="Executive Overview"
        subtitle={overview.data ? `Latest available billing date ${periodText({ start: overview.data.meta.as_of, end: overview.data.meta.as_of })} · ${currency} · ${overview.data.meta.cost_type === "actual" ? "Actual cost" : "Amortized cost"}` : "Azure expenditure across applications, environments and subscriptions"}
      />
      <Stack spacing={2}>
        <Warnings warnings={overview.data?.meta.warnings.filter((w) => !w.startsWith("The current period is incomplete"))} />
        {overview.error ? (
          <ErrorState error={overview.error} onRetry={() => overview.refetch()} />
        ) : (
          <Grid container spacing={1.5} data-testid="kpi-grid">
            {(kpis.length ? kpis : Array.from({ length: 12 }, (_, i) => ({ key: `s${i}` }) as Kpi)).map((k) => (
              <Grid key={k.key} size={{ xs: 12, sm: 6, md: 4, lg: 3, xl: 2 }}>
                {k.title ? (
                  <KpiCard kpi={k} currency={currency} href={KPI_LINKS[k.key]?.(link)} spark={k.sparkline && spark ? spark[k.sparkline]?.map((p) => p.value) : undefined} />
                ) : (
                  <Box sx={{ height: 118, border: `1px solid ${surface.border}`, borderRadius: 1, bgcolor: "#fff" }} />
                )}
              </Grid>
            ))}
          </Grid>
        )}

        <Section
          title="Azure expenditure trend"
          subtitle={trend.data ? `${periodText(trend.data.meta.period)} vs ${periodText(trend.data.meta.comparison_period)}${trend.data.data.budget_name ? ` · budget: ${trend.data.data.budget_name}` : ""}${trend.data.data.forecast ? ` · forecast: ${trend.data.data.forecast.method_label}` : ""}` : " "}
          testId="trend"
          actions={
            <ToggleButtonGroup size="small" exclusive value={local.gran} onChange={(_, v) => v && setLocal({ gran: v })} aria-label="Granularity">
              <ToggleButton value="daily">Daily</ToggleButton>
              <ToggleButton value="weekly">Weekly</ToggleButton>
              <ToggleButton value="monthly">Monthly</ToggleButton>
            </ToggleButtonGroup>
          }
          table={<DataTable data={trendRows} columns={trendColumns} maxHeight={360} storageKey="overview-trend" />}
        >
          {trend.error ? <ErrorState error={trend.error} onRetry={() => trend.refetch()} /> : trendOpt ? <EChart option={trendOpt} height={300} ariaLabel="Expenditure trend with previous period, budget and forecast" /> : <ChartSkeleton height={300} />}
          {trend.data?.data.forecast && (
            <Typography variant="caption" sx={{ display: "block", mt: 0.5 }}>
              Forecast is a projection ({trend.data.data.forecast.method_label}); month-end forecast {money(trend.data.data.forecast.forecast_total, currency)}. Forecast values are never actual charges.
            </Typography>
          )}
        </Section>

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 7 }}>
            <BreakdownCard dim="service_category" title="Service-wise expenditure" chart="grouped" params={apiParams} labelHeader="Azure service" onPick={pick("service_category")} />
          </Grid>
          <Grid size={{ xs: 12, lg: 5 }}>
            <BreakdownCard dim="environment" title="Environment-wise expenditure" chart="donut" params={apiParams} labelHeader="Environment" onPick={pick("environment")} />
          </Grid>
          <Grid size={{ xs: 12, lg: 6 }}>
            <BreakdownCard dim="application" title="Application-wise expenditure" chart="grouped" params={apiParams} labelHeader="Application" onPick={pick("application")} />
          </Grid>
          <Grid size={{ xs: 12, lg: 6 }}>
            <BreakdownCard dim="subscription" title="Subscription-wise expenditure" chart="grouped" params={apiParams} labelHeader="Subscription" onPick={pick("subscription")} />
          </Grid>
          <Grid size={{ xs: 12, lg: 6 }}>
            <Section
              title="Largest cost changes by service"
              subtitle="Absolute change vs comparison period (increases red, decreases blue)"
              testId="service-movers"
              table={<DataTable data={serviceMoverRows} columns={comparisonColumns({ currency, hasComparison: true, labelHeader: "Azure service" })} defaultHidden={["previous_daily_avg", "current_records", "current_daily_avg", "share_of_total"]} storageKey="overview-svc-movers" />}
            >
              {serviceMovers.error ? <ErrorState error={serviceMovers.error} /> : serviceMoverOpt ? <EChart option={serviceMoverOpt} height={280} ariaLabel="Service cost changes" /> : <ChartSkeleton height={280} />}
            </Section>
          </Grid>
          <Grid size={{ xs: 12, lg: 6 }}>
            <Section
              title="Largest cost changes by resource"
              subtitle="Top 10 resources ranked by absolute change (not percentage)"
              testId="resource-movers"
              table={<DataTable data={movers.data?.data ?? []} columns={moverCols} defaultHidden={["previous_daily_avg", "current_records", "current_daily_avg", "share_of_total"]} storageKey="overview-res-movers" />}
            >
              {movers.error ? <ErrorState error={movers.error} /> : moverOpt ? <EChart option={moverOpt} height={280} ariaLabel="Resource cost changes" /> : <ChartSkeleton height={280} />}
            </Section>
          </Grid>
        </Grid>

        <Section title="Budget consumption" subtitle="Month-to-date actual vs budget, with forecast month-end projection" testId="budget-consumption" actions={<Link href={link("/budgets")} style={{ fontSize: 12.5, fontWeight: 600, color: "#0f6cbd" }}>Manage budgets</Link>}>
          {budgets.error ? (
            <ErrorState error={budgets.error} />
          ) : !budgets.data ? (
            <ChartSkeleton height={120} />
          ) : budgets.data.data.length === 0 ? (
            <EmptyState title="No budgets configured" message="Create budgets on the Budget & Forecast page." />
          ) : (
            <Grid container spacing={2}>
              {budgets.data.data.filter((b) => b.period_type === "monthly").map((b) => {
                const u = b.utilization_pct ?? 0;
                const fu = b.forecast_utilization_pct ?? 0;
                return (
                  <Grid key={b.id} size={{ xs: 12, md: 6, xl: 4 }}>
                    <Box sx={{ p: 1.25, border: `1px solid ${surface.border}`, borderRadius: 1 }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="baseline">
                        <Typography variant="subtitle1" noWrap title={b.name}>{b.scope_label}</Typography>
                        <Typography variant="caption">{pct(u, { sign: false })} used</Typography>
                      </Stack>
                      <Tooltip title={`Forecast ${money(b.forecast, b.currency)} (${pct(fu, { sign: false })} of budget)`}>
                        <Box sx={{ position: "relative", mt: 0.75 }}>
                          <LinearProgress variant="determinate" value={Math.min(u, 100)} sx={{ height: 8, bgcolor: "#e3eefb", "& .MuiLinearProgress-bar": { bgcolor: u >= 100 ? "#d03b3b" : u >= 90 ? "#ec835a" : "#2a78d6" } }} aria-label={`${b.scope_label} budget utilisation`} />
                          <Box sx={{ position: "absolute", top: -3, bottom: -3, left: `${Math.min(fu, 100)}%`, width: 2, bgcolor: b.forecast_exceeds_budget ? "#d03b3b" : "#52514e" }} aria-hidden />
                        </Box>
                      </Tooltip>
                      <Stack direction="row" justifyContent="space-between" sx={{ mt: 0.75 }}>
                        <Typography variant="caption">Actual <b>{compactMoney(b.actual, b.currency)}</b> of {compactMoney(b.amount, b.currency)}</Typography>
                        <Typography variant="caption" sx={{ color: b.forecast_exceeds_budget ? "#b42318" : "text.secondary", fontWeight: b.forecast_exceeds_budget ? 600 : 400 }}>
                          Forecast {compactMoney(b.forecast, b.currency)}{b.forecast_exceeds_budget ? " · over budget" : ""}
                        </Typography>
                      </Stack>
                    </Box>
                  </Grid>
                );
              })}
            </Grid>
          )}
        </Section>
      </Stack>
    </Box>
  );
}
