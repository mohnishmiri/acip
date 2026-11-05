"use client";
/**
 * Interactive Cost Explorer.
 *
 * One API call (/costs/explorer) returns grouped comparison rows, the time series and the
 * reconciled waterfall. Every visualisation and the table render from that same result,
 * so switching chart type never refetches and never resets filters. All explorer state
 * (chart, view, grouping, granularity, comparison, drill path) lives in the URL.
 */
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import BarChartIcon from "@mui/icons-material/BarChart";
import DonutLargeIcon from "@mui/icons-material/DonutLarge";
import NavigateNextIcon from "@mui/icons-material/NavigateNext";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import StackedBarChartIcon from "@mui/icons-material/StackedBarChart";
import StackedLineChartIcon from "@mui/icons-material/StackedLineChart";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import AreaChartIcon from "@mui/icons-material/AreaChart";
import WaterfallChartIcon from "@mui/icons-material/WaterfallChart";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import AlignVerticalBottomIcon from "@mui/icons-material/AlignVerticalBottom";
import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  Divider,
  FormControl,
  InputLabel,
  Link as MuiLink,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { useRouter } from "next/navigation";
import { useCallback, useMemo } from "react";
import EChart from "@/charts/EChart";
import { barOption, donutOption, timeSeriesOption, treemapOption, waterfallOption } from "@/charts/options";
import { DeltaText } from "@/components/common/Delta";
import { ExportMenu } from "@/components/common/ExportMenu";
import { PageHeader } from "@/components/common/PageHeader";
import { ChartSkeleton, EmptyState, ErrorState, Warnings } from "@/components/common/States";
import { GlobalFilterBar } from "@/components/layout/GlobalFilters";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { useUrlState } from "@/hooks/useUrlState";
import { DIM_LABEL, drillParams, parseDrill, resourceIdFor, type DrillStep } from "@/lib/drill";
import { money, pct, periodText } from "@/lib/format";
import type { GroupItem } from "@/lib/types";
import { useExplorer, useFilterOptions } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { comparisonColumns } from "@/tables/columns";
import { surface } from "@/styles/tokens";

export const CHARTS = [
  { value: "bar", label: "Bar", icon: BarChartIcon },
  { value: "grouped", label: "Grouped bar", icon: AlignVerticalBottomIcon },
  { value: "stacked", label: "Stacked bar", icon: StackedBarChartIcon },
  { value: "line", label: "Line", icon: ShowChartIcon },
  { value: "area", label: "Area", icon: AreaChartIcon },
  { value: "stacked_area", label: "Stacked area", icon: StackedLineChartIcon },
  { value: "waterfall", label: "Waterfall", icon: WaterfallChartIcon },
  { value: "donut", label: "Donut", icon: DonutLargeIcon },
  { value: "treemap", label: "Treemap", icon: AccountTreeOutlinedIcon },
  { value: "table", label: "Table", icon: TableChartOutlinedIcon },
] as const;

const EXPLORER_DEFAULTS = { chart: "bar", view: "split", group: "service_category", gran: "daily", cmp: "previous_equivalent", cs: "", ce: "", top: "", tag: "", drill: "" };

function Stat({ label, value, sub, testId }: { label: string; value: React.ReactNode; sub?: React.ReactNode; testId?: string }) {
  return (
    <Box sx={{ px: 2, py: 1, minWidth: 140 }} data-testid={testId}>
      <Typography variant="caption" component="div">
        {label}
      </Typography>
      <Typography sx={{ fontSize: 17, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{value}</Typography>
      {sub && (
        <Typography variant="caption" component="div">
          {sub}
        </Typography>
      )}
    </Box>
  );
}

export default function ExplorerPage() {
  const router = useRouter();
  const link = useLinkWithFilters();
  const { filters, apiParams, setFilters } = useGlobalFilters();
  const [s, set] = useUrlState(EXPLORER_DEFAULTS);
  const opts = useFilterOptions();
  const drill = useMemo(() => parseDrill(s.drill), [s.drill]);

  const params = useMemo(
    () => ({
      ...apiParams,
      ...drillParams(drill),
      group_by: s.group,
      tag_key: s.group === "tag" ? s.tag || opts.data?.tag_keys[0] : undefined,
      granularity: s.gran,
      comparison: s.cmp,
      compare_start_date: s.cmp === "custom" ? s.cs : undefined,
      compare_end_date: s.cmp === "custom" ? s.ce : undefined,
      top_n: s.top ? Number(s.top) : undefined,
    }),
    [apiParams, drill, s.group, s.tag, s.gran, s.cmp, s.cs, s.ce, s.top, opts.data],
  );
  const ready = !(s.group === "tag" && !params.tag_key) && !(s.cmp === "custom" && (!s.cs || !s.ce));
  const q = useExplorer(ready ? params : { ...params, comparison: "none" });
  const d = q.data?.data;
  const meta = q.data?.meta;
  const currency = meta?.currency ?? "USD";
  const hasCmp = !!meta?.comparison_period;
  const chart = s.chart;
  const view = chart === "table" ? "table" : s.view;

  const drillInto = useCallback(
    async (g: GroupItem) => {
      if (!d || g.key === "__other__") return;
      if (d.group_by === "resource") {
        const id = g.key ? await resourceIdFor(g.key, apiParams) : null;
        if (id) router.push(link(`/resources/${id}`));
        return;
      }
      if (d.group_by === "meter") return; // finest level; meter-level analysis lives on the resource page
      const step: DrillStep = { dim: d.group_by, key: g.key, label: g.label, tagKey: d.group_by === "tag" ? (params.tag_key as string) : undefined, fromGroup: d.group_by };
      const next = d.next_level ?? "resource";
      set({ drill: JSON.stringify([...drill, step]), group: next });
    },
    [d, drill, set, router, link, apiParams, params.tag_key],
  );

  const goToLevel = (n: number) => {
    const steps = drill.slice(0, n);
    const restore = drill[n]?.fromGroup ?? s.group;
    set({ drill: steps.length ? JSON.stringify(steps) : "", group: restore });
  };

  const option = useMemo(() => {
    if (!d) return null;
    const dim = d.group_by;
    switch (chart) {
      case "bar":
        return barOption(d.groups, { currency, grouped: false, hasComparison: hasCmp });
      case "grouped":
        return barOption(d.groups, { currency, grouped: true, hasComparison: hasCmp });
      case "stacked":
        return timeSeriesOption(d.series, { currency, stacked: true, area: false, kind: "bar", byGroup: true, dimension: dim, zoom: d.series.buckets.length > 31 });
      case "line":
        return timeSeriesOption(d.series, { currency, stacked: false, area: false, kind: "line", byGroup: false, dimension: dim, zoom: d.series.buckets.length > 31 });
      case "area":
        return timeSeriesOption(d.series, { currency, stacked: false, area: true, kind: "line", byGroup: false, dimension: dim, zoom: d.series.buckets.length > 31 });
      case "stacked_area":
        return timeSeriesOption(d.series, { currency, stacked: true, area: true, kind: "line", byGroup: true, dimension: dim, zoom: d.series.buckets.length > 31 });
      case "waterfall":
        return d.waterfall ? waterfallOption(d.waterfall, currency) : null;
      case "donut":
        return donutOption(d.groups, { currency, dimension: dim });
      case "treemap":
        return treemapOption(d.groups, { currency, dimension: dim });
      default:
        return null;
    }
  }, [d, chart, currency, hasCmp]);

  const onChartClick = useCallback(
    (p: { name: string; seriesName?: string; data: unknown }) => {
      if (!d) return;
      let key: string | undefined;
      const data = p.data as { key?: string } | null;
      if (data && typeof data === "object" && data.key) key = data.key;
      if (!key && (chart === "stacked" || chart === "stacked_area")) key = d.series.series.find((x) => x.label === p.seriesName)?.key;
      const g = key ? d.groups.find((x) => x.key === key) : d.groups.find((x) => x.label === p.name);
      if (g) drillInto(g);
    },
    [d, chart, drillInto],
  );

  const columns = useMemo(() => comparisonColumns({ currency, hasComparison: hasCmp, labelHeader: d?.group_by_label ?? "Group", onLabelClick: drillInto }), [currency, hasCmp, d?.group_by_label, drillInto]);

  // Breadcrumb: global scope first, then drill steps
  const appName = filters.app ? (opts.data?.applications.find((a) => String(a.id) === filters.app)?.name ?? (filters.app === "shared" ? "Shared Services" : filters.app === "unallocated" ? "Unallocated" : filters.app)) : "All Applications";
  const envName = filters.env ? (opts.data?.environment_groups.find((e) => e.code === filters.env)?.name ?? filters.env) : null;
  const subName = filters.sub ? (opts.data?.subscriptions.find((x) => x.subscription_id === filters.sub)?.subscription_name ?? filters.sub) : null;

  const chartTitle = CHARTS.find((c) => c.value === chart)?.label ?? "";
  const waterfallMissing = chart === "waterfall" && !hasCmp;
  const timeChart = ["stacked", "line", "area", "stacked_area"].includes(chart);

  return (
    <Box>
      <PageHeader
        title="Cost Explorer"
        subtitle="Analyse expenditure by any dimension; switch visualisations without losing filters; click a group to drill down."
        actions={
          <>
            <Button
              variant="outlined"
              color="inherit"
              startIcon={<RestartAltIcon fontSize="small" />}
              onClick={() => {
                set({ ...EXPLORER_DEFAULTS });
                setFilters({ app: "", env: "", sub: "", preset: "last_30_days", start: "", end: "", cost: "actual", cur: "" });
              }}
              data-testid="reset-filters"
            >
              Reset filters
            </Button>
            <ExportMenu params={params} view="explorer" label="Download table" />
          </>
        }
      />

      <Paper variant="outlined" sx={{ mb: 2 }} data-testid="explorer-toolbar">
        <Box sx={{ px: 1.5, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
          <GlobalFilterBar />
        </Box>
        <Stack direction="row" spacing={1.25} alignItems="center" flexWrap="wrap" useFlexGap sx={{ px: 1.5, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
          <FormControl sx={{ minWidth: 170 }}>
            <InputLabel id="gb">Group by</InputLabel>
            <Select labelId="gb" label="Group by" value={s.group} onChange={(e) => set({ group: e.target.value })} data-testid="group-by">
              {(opts.data?.group_by ?? []).map((g) => (
                <MenuItem key={g.value} value={g.value}>
                  {g.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {s.group === "tag" && (
            <FormControl sx={{ minWidth: 150 }}>
              <InputLabel id="tk">Tag key</InputLabel>
              <Select labelId="tk" label="Tag key" value={(params.tag_key as string) ?? ""} onChange={(e) => set({ tag: e.target.value })}>
                {(opts.data?.tag_keys ?? []).map((k) => (
                  <MenuItem key={k} value={k}>
                    {k}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
          <ToggleButtonGroup size="small" exclusive value={s.gran} onChange={(_, v) => v && set({ gran: v })} aria-label="Granularity">
            <ToggleButton value="daily" data-testid="gran-daily">Daily</ToggleButton>
            <ToggleButton value="weekly" data-testid="gran-weekly">Weekly</ToggleButton>
            <ToggleButton value="monthly" data-testid="gran-monthly">Monthly</ToggleButton>
          </ToggleButtonGroup>
          <FormControl sx={{ minWidth: 220 }}>
            <InputLabel id="cmp">Comparison</InputLabel>
            <Select labelId="cmp" label="Comparison" value={s.cmp} onChange={(e) => set({ cmp: e.target.value })} data-testid="comparison">
              {(opts.data?.comparison_modes ?? []).map((m) => (
                <MenuItem key={m.value} value={m.value}>
                  {m.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {s.cmp === "custom" && (
            <>
              <TextField type="date" label="Compare from" value={s.cs} onChange={(e) => set({ cs: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
              <TextField type="date" label="Compare to" value={s.ce} onChange={(e) => set({ ce: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
            </>
          )}
          {chart === "waterfall" && (
            <FormControl sx={{ minWidth: 130 }}>
              <InputLabel id="topn">Contributors</InputLabel>
              <Select labelId="topn" label="Contributors" value={s.top || String(opts.data?.default_waterfall_top_n ?? 4)} onChange={(e) => set({ top: e.target.value })}>
                {[3, 4, 5, 6, 8, 10, 15].map((n) => (
                  <MenuItem key={n} value={String(n)}>
                    Top {n} + Other
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
        </Stack>
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ px: 1.5, py: 1 }}>
          <Typography variant="subtitle2">Visualisation</Typography>
          <ToggleButtonGroup size="small" exclusive value={chart} onChange={(_, v) => v && set({ chart: v })} aria-label="Visualisation type" data-testid="chart-type">
            {CHARTS.map((c) => {
              const Icon = c.icon;
              return (
                <ToggleButton key={c.value} value={c.value} aria-label={c.label} title={c.label} data-testid={`chart-${c.value}`} sx={{ gap: 0.5 }}>
                  <Icon sx={{ fontSize: 16 }} />
                  <Box component="span" sx={{ display: { xs: "none", xl: "inline" } }}>
                    {c.label}
                  </Box>
                </ToggleButton>
              );
            })}
          </ToggleButtonGroup>
          <Box sx={{ flex: 1 }} />
          <ToggleButtonGroup size="small" exclusive value={view} onChange={(_, v) => v && set({ view: v })} aria-label="Layout" disabled={chart === "table"} data-testid="view-mode">
            <ToggleButton value="chart">Chart</ToggleButton>
            <ToggleButton value="table">Table</ToggleButton>
            <ToggleButton value="split">Split</ToggleButton>
          </ToggleButtonGroup>
        </Stack>
      </Paper>

      <Stack spacing={1.5}>
        <Stack direction="row" alignItems="center" spacing={1}>
          {drill.length > 0 && (
            <Button size="small" startIcon={<ArrowBackIcon fontSize="small" />} onClick={() => goToLevel(drill.length - 1)} data-testid="drill-back">
              Back
            </Button>
          )}
          <Breadcrumbs separator={<NavigateNextIcon sx={{ fontSize: 16 }} />} aria-label="Drill-down path" data-testid="breadcrumb">
            <MuiLink component="button" underline="hover" color={drill.length ? "primary" : "text.primary"} onClick={() => goToLevel(0)} sx={{ fontSize: 13, fontWeight: 600 }}>
              {appName}
            </MuiLink>
            {envName && <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{envName}</Typography>}
            {subName && <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{subName}</Typography>}
            {drill.map((step, i) => (
              <MuiLink key={`${step.dim}-${i}`} component="button" underline="hover" color={i === drill.length - 1 ? "text.primary" : "primary"} onClick={() => goToLevel(i + 1)} sx={{ fontSize: 13, fontWeight: 600 }} title={DIM_LABEL[step.dim]}>
                {step.label}
              </MuiLink>
            ))}
            <Typography sx={{ fontSize: 13, color: "text.secondary" }}>by {d?.group_by_label ?? DIM_LABEL[s.group]}</Typography>
          </Breadcrumbs>
          {drill.length > 0 && <Chip label={`${drill.length} drill filter${drill.length > 1 ? "s" : ""}`} onDelete={() => goToLevel(0)} variant="outlined" />}
        </Stack>

        <Warnings warnings={meta?.warnings} />

        <Paper variant="outlined" sx={{ display: "flex", flexWrap: "wrap", alignItems: "stretch" }} data-testid="explorer-totals">
          <Stat label={`Current · ${meta ? periodText(meta.period) : "…"}`} value={d ? money(d.totals.current, currency) : "…"} testId="total-current" sub={meta?.period.is_incomplete ? `${meta.period.days} of ${meta.period.nominal_end ? "the period's" : ""} days available` : undefined} />
          <Divider orientation="vertical" flexItem />
          <Stat label={hasCmp ? `Previous · ${periodText(meta?.comparison_period)}` : "Comparison"} value={hasCmp && d ? money(d.totals.previous, currency) : "None"} testId="total-previous" />
          <Divider orientation="vertical" flexItem />
          <Stat label="Difference" value={hasCmp && d ? <DeltaText value={d.totals.diff} currency={currency} /> : "—"} testId="total-diff" sub={hasCmp && d ? (d.totals.significance === "normal" ? "Within normal variation" : d.totals.significance === "notable_increase" ? "Notable increase" : d.totals.significance === "notable_decrease" ? "Notable decrease" : undefined) : undefined} />
          <Divider orientation="vertical" flexItem />
          <Stat label="Change %" value={hasCmp && d ? <DeltaText value={d.totals.pct} kind="pct" /> : "—"} testId="total-pct" />
          <Divider orientation="vertical" flexItem />
          <Stat label="Daily average" value={d ? money(d.totals.current_daily_avg, currency) : "…"} sub={hasCmp && d ? `previous ${money(d.totals.previous_daily_avg, currency)}` : undefined} />
          {d?.totals.run_rate !== null && d?.totals.run_rate !== undefined && (
            <>
              <Divider orientation="vertical" flexItem />
              <Stat label="Estimated run rate (full period)" value={money(d.totals.run_rate, currency)} sub="Projection, not actual" />
            </>
          )}
          <Box sx={{ flex: 1 }} />
          <Stat label={d?.group_by_label ?? "Groups"} value={d ? d.group_count.toLocaleString() : "…"} sub={`${currency} · ${meta?.cost_type === "amortized" ? "Amortized" : "Actual"} cost`} />
        </Paper>

        {q.error ? (
          <Paper variant="outlined">
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          </Paper>
        ) : (
          <>
            {view !== "table" && (
              <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="explorer-chart">
                <Stack direction="row" alignItems="baseline" spacing={1} sx={{ mb: 1 }}>
                  <Typography variant="h3">
                    {chartTitle} · {d?.group_by_label ?? ""}
                  </Typography>
                  <Typography variant="caption">
                    {chart === "waterfall"
                      ? "How the previous period total became the current total. Axis does not start at zero."
                      : timeChart
                        ? `${d?.series.granularity ?? s.gran} buckets${chart === "line" || chart === "area" ? " · current vs previous period" : " · top 8 groups + Other"}`
                        : chart === "donut" || chart === "treemap"
                          ? "Share of current-period cost · top 8 + Other"
                          : hasCmp
                            ? "Click a bar to drill down"
                            : "Click a bar to drill down"}
                  </Typography>
                </Stack>
                {waterfallMissing ? (
                  <Alert severity="info">The waterfall explains a change between two periods. Select a comparison period above.</Alert>
                ) : !option ? (
                  <ChartSkeleton height={340} />
                ) : d && d.groups.length === 0 ? (
                  <EmptyState message="No cost in the selected period and filters." />
                ) : (
                  <EChart option={option} height={360} ariaLabel={`${chartTitle} of cost by ${d?.group_by_label}`} onClick={onChartClick} testId={`echart-${chart}`} />
                )}
                {chart === "waterfall" && d?.waterfall && (
                  <Typography variant="caption" sx={{ display: "block", mt: 0.5 }} data-testid="waterfall-reconciliation">
                    {money(d.waterfall.previous_total, currency)} {d.waterfall.net_change >= 0 ? "+" : "−"} {money(Math.abs(d.waterfall.net_change), currency)} ({pct(d.waterfall.pct_change)}) = {money(d.waterfall.current_total, currency)} ·{" "}
                    {d.waterfall.reconciled ? "Reconciled exactly with the underlying comparison." : `Reconciliation difference ${money(d.waterfall.reconciliation_difference, currency)}`}
                  </Typography>
                )}
              </Paper>
            )}
            {view !== "chart" && (
              <Paper variant="outlined" data-testid="explorer-table">
                <DataTable
                  data={d?.groups ?? []}
                  columns={columns}
                  loading={q.isFetching}
                  onRowClick={drillInto}
                  getRowId={(r) => r.key || "__none__"}
                  storageKey={`explorer-${s.group}`}
                  defaultHidden={["previous_daily_avg", "current_records"]}
                  clientPageSize={50}
                  maxHeight={view === "table" ? 680 : 480}
                  toolbar={
                    <Typography variant="body2" color="text.secondary">
                      {d ? `${d.groups.length.toLocaleString()} rows${d.groups_truncated ? " (largest 500 shown; remainder grouped as Other)" : ""}` : ""}
                      {d?.group_by === "resource" ? " · click a resource to open its analysis" : d?.next_level ? ` · click a row to drill into ${DIM_LABEL[d.next_level]}` : ""}
                    </Typography>
                  }
                  testId="explorer-grid"
                />
              </Paper>
            )}
          </>
        )}
      </Stack>
    </Box>
  );
}
