"use client";
/**
 * Cost Comparison: period-vs-period comparison with a reconciled waterfall, a matching
 * contribution table and hierarchical drill-down
 * Application -> Environment -> Subscription -> Azure Service -> Resource Group -> Resource -> Meter.
 */
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import EChart from "@/charts/EChart";
import { waterfallOption } from "@/charts/options";
import { DeltaText, MoneyText } from "@/components/common/Delta";
import { ExportMenu } from "@/components/common/ExportMenu";
import { PageHeader } from "@/components/common/PageHeader";
import { Section } from "@/components/common/Section";
import { StatusChip } from "@/components/common/StatusChip";
import { ChartSkeleton, EmptyState, ErrorState, Warnings } from "@/components/common/States";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { useUrlState } from "@/hooks/useUrlState";
import { DIM_LABEL, drillParams, parseDrill, resourceIdFor, type DrillStep } from "@/lib/drill";
import { money, pct, periodText } from "@/lib/format";
import type { Envelope, GroupItem, Totals, Waterfall, WaterfallStep } from "@/lib/types";
import { useApi, useFilterOptions } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { comparisonColumns } from "@/tables/columns";
import { DrillBreadcrumb, RecordsTable, Stat, StatStrip } from "./shared";

interface CompareData {
  group_by: string;
  group_by_label: string;
  next_level: string | null;
  filter_param: string | null;
  totals: Totals;
  waterfall: Waterfall;
  groups: GroupItem[];
  group_count: number;
  summary: { increased_count: number; decreased_count: number; new_count: number; removed_count: number; gross_increase: number; gross_decrease: number; net_change: number };
}

/** Drill hierarchy for the comparison page (resource drills into its billing meters). */
const HIERARCHY: Record<string, string | null> = {
  application: "environment",
  environment: "subscription",
  subscription: "service_category",
  service_category: "resource_group",
  resource_group: "resource",
  resource: "meter",
  meter_category: "meter_name",
  resource_type: "resource",
  region: "service_category",
  owner: "resource",
  cost_center: "resource",
  sku: "resource",
  charge_type: "service_category",
  pricing_model: "service_category",
  meter_name: null,
  meter: null,
};

const SHORTCUTS = [
  { label: "Day", preset: "today" },
  { label: "Week", preset: "week_to_date" },
  { label: "Month", preset: "month_to_date" },
  { label: "Quarter", preset: "quarter_to_date" },
  { label: "Year", preset: "year_to_date" },
  { label: "Previous week", preset: "previous_week" },
  { label: "Previous month", preset: "previous_month" },
];

const SORTS = [
  { value: "abs_diff", label: "Largest absolute change" },
  { value: "pct_increase", label: "Highest % increase" },
  { value: "largest_decrease", label: "Largest decrease" },
  { value: "current_cost", label: "Highest current cost" },
  { value: "contribution", label: "Highest contribution to increase" },
];

const DEFAULTS = { basis: "previous_equivalent", cs: "", ce: "", group: "service_category", top: "", sort: "abs_diff", drill: "", records: "" };

export default function ComparisonPage() {
  const router = useRouter();
  const link = useLinkWithFilters();
  const { filters, setFilters, apiParams } = useGlobalFilters();
  const [s, set] = useUrlState(DEFAULTS);
  const opts = useFilterOptions().data;
  const drill = useMemo(() => parseDrill(s.drill), [s.drill]);
  const [customStart, setCustomStart] = useState(filters.start);
  const [customEnd, setCustomEnd] = useState(filters.end);

  const params = useMemo(
    () => ({
      ...apiParams,
      ...drillParams(drill),
      group_by: s.group,
      comparison: s.basis,
      compare_start_date: s.basis === "custom" ? s.cs : undefined,
      compare_end_date: s.basis === "custom" ? s.ce : undefined,
      top_n: s.top ? Number(s.top) : undefined,
      sort: s.sort,
    }),
    [apiParams, drill, s.group, s.basis, s.cs, s.ce, s.top, s.sort],
  );
  const ready = !(s.basis === "custom" && (!s.cs || !s.ce));
  const q = useApi<Envelope<CompareData>>(ready ? "/costs/compare" : null, params);
  const d = q.data?.data;
  const meta = q.data?.meta;
  const currency = meta?.currency ?? "USD";

  const drillInto = useCallback(
    (g: GroupItem) => {
      if (!d || g.key === "__other__" || g.key.startsWith("__")) return;
      const next = HIERARCHY[d.group_by] ?? (d.group_by === "resource" ? "meter" : "resource");
      if (next === null) {
        set({ records: "1" });
        return;
      }
      const step: DrillStep = { dim: d.group_by, key: g.key, label: g.label, fromGroup: d.group_by };
      set({ drill: JSON.stringify([...drill, step]), group: next });
    },
    [d, drill, set],
  );

  const goToLevel = (n: number) => {
    const restore = drill[n]?.fromGroup ?? s.group;
    set({ drill: n ? JSON.stringify(drill.slice(0, n)) : "", group: restore });
  };

  const currentResourceKey = [...drill].reverse().find((x) => x.dim === "resource")?.key;
  const openResource = async () => {
    if (!currentResourceKey) return;
    const id = await resourceIdFor(currentResourceKey, apiParams);
    if (id) router.push(link(`/resources/${id}`));
  };

  const wfOption = useMemo(() => (d ? waterfallOption(d.waterfall, currency) : null), [d, currency]);
  const columns = useMemo(() => comparisonColumns({ currency, hasComparison: true, labelHeader: d?.group_by_label ?? "Group", onLabelClick: drillInto }), [currency, d?.group_by_label, drillInto]);
  const stepCols = useMemo<ColumnDef<WaterfallStep, unknown>[]>(
    () => [
      { accessorKey: "label", header: "Step", size: 260 },
      { accessorKey: "kind", header: "Type", size: 110, cell: ({ getValue }) => <StatusChip value={getValue() as string} tone="neutral" /> },
      { accessorKey: "value", header: "Contribution", size: 140, meta: { numeric: true }, cell: ({ row }) => (row.original.kind === "start" || row.original.kind === "end" ? <MoneyText value={row.original.value} currency={currency} bold /> : <DeltaText value={row.original.value} currency={currency} />) },
      { accessorKey: "previous", header: "Previous", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number | null} currency={currency} /> },
      { accessorKey: "current", header: "Current", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number | null} currency={currency} /> },
      { accessorKey: "pct", header: "Change %", size: 100, meta: { numeric: true }, cell: ({ row }) => <DeltaText value={row.original.pct} kind="pct" status={row.original.status} /> },
      { accessorKey: "start", header: "Running from", size: 130, meta: { numeric: true }, cell: ({ getValue }) => money(getValue() as number, currency) },
      { accessorKey: "end", header: "Running to", size: 130, meta: { numeric: true }, cell: ({ getValue }) => money(getValue() as number, currency) },
    ],
    [currency],
  );

  const onChartClick = (p: { data: unknown; name: string }) => {
    const key = (p.data as { key?: string } | null)?.key;
    const g = d?.groups.find((x) => x.key === key) ?? d?.groups.find((x) => x.label === p.name);
    if (g) drillInto(g);
  };

  const groupOptions = (opts?.group_by ?? []).filter((g) => g.value !== "tag");
  const summary = d?.summary;

  return (
    <Box data-testid="comparison-page">
      <PageHeader
        title="Cost Comparison"
        subtitle="Explain why expenditure changed between two periods — every waterfall reconciles exactly with the underlying billing records."
        actions={<ExportMenu params={params} view="compare" label="Download contributions" />}
      />

      <Paper variant="outlined" sx={{ mb: 2 }} data-testid="comparison-toolbar">
        <Stack direction="row" spacing={1.25} alignItems="center" flexWrap="wrap" useFlexGap sx={{ px: 1.5, py: 1.25 }}>
          <Typography variant="subtitle2">Compare</Typography>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={SHORTCUTS.some((x) => x.preset === filters.preset) ? filters.preset : filters.preset === "custom" ? "custom" : null}
            onChange={(_, v) => v && v !== "custom" && setFilters({ preset: v, start: "", end: "" })}
            aria-label="Period"
            data-testid="period-shortcuts"
          >
            {SHORTCUTS.map((x) => (
              <ToggleButton key={x.preset} value={x.preset} data-testid={`period-${x.preset}`}>
                {x.label}
              </ToggleButton>
            ))}
            <ToggleButton value="custom" disabled={filters.preset !== "custom"}>
              Custom
            </ToggleButton>
          </ToggleButtonGroup>
          <TextField type="date" label="From" value={customStart} onChange={(e) => setCustomStart(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} sx={{ width: 150 }} />
          <TextField type="date" label="To" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} sx={{ width: 150 }} />
          <Button variant="outlined" color="inherit" disabled={!customStart || !customEnd || customEnd < customStart} onClick={() => setFilters({ preset: "custom", start: customStart, end: customEnd })}>
            Apply range
          </Button>
        </Stack>
        <Stack direction="row" spacing={1.25} alignItems="center" flexWrap="wrap" useFlexGap sx={{ px: 1.5, py: 1.25, borderTop: 1, borderColor: "divider" }}>
          <FormControl sx={{ minWidth: 250 }}>
            <InputLabel id="basis">Compared with</InputLabel>
            <Select labelId="basis" label="Compared with" value={s.basis} onChange={(e) => set({ basis: e.target.value })} data-testid="comparison-basis">
              <MenuItem value="previous_equivalent">Previous period — equivalent elapsed days</MenuItem>
              <MenuItem value="previous_calendar">Previous period — full calendar period</MenuItem>
              <MenuItem value="same_period_last_year">Same period last year</MenuItem>
              <MenuItem value="custom">Custom comparison range</MenuItem>
            </Select>
          </FormControl>
          {s.basis === "custom" && (
            <>
              <TextField type="date" label="Compare from" value={s.cs} onChange={(e) => set({ cs: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
              <TextField type="date" label="Compare to" value={s.ce} onChange={(e) => set({ ce: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
            </>
          )}
          <FormControl sx={{ minWidth: 170 }}>
            <InputLabel id="cgb">Group by</InputLabel>
            <Select labelId="cgb" label="Group by" value={s.group} onChange={(e) => set({ group: e.target.value })} data-testid="comparison-group-by">
              {groupOptions.map((g) => (
                <MenuItem key={g.value} value={g.value}>
                  {g.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl sx={{ minWidth: 140 }}>
            <InputLabel id="ctop">Waterfall</InputLabel>
            <Select labelId="ctop" label="Waterfall" value={s.top || String(opts?.default_waterfall_top_n ?? 4)} onChange={(e) => set({ top: e.target.value })} data-testid="comparison-top-n">
              {[3, 4, 5, 6, 8, 10, 15].map((n) => (
                <MenuItem key={n} value={String(n)}>
                  Top {n} + Other
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl sx={{ minWidth: 230 }}>
            <InputLabel id="csort">Sort contributions</InputLabel>
            <Select labelId="csort" label="Sort contributions" value={s.sort} onChange={(e) => set({ sort: e.target.value })} data-testid="comparison-sort">
              {SORTS.map((x) => (
                <MenuItem key={x.value} value={x.value}>
                  {x.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
      </Paper>

      <Stack spacing={1.5}>
        <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
          <DrillBreadcrumb drill={drill} groupLabel={d?.group_by_label ?? DIM_LABEL[s.group]} onLevel={goToLevel} />
          {currentResourceKey && (
            <Button size="small" variant="outlined" endIcon={<OpenInNewIcon sx={{ fontSize: 14 }} />} onClick={openResource} data-testid="open-resource">
              Open resource analysis
            </Button>
          )}
          {drill.length > 0 && <Chip label={`${drill.length} drill filter${drill.length > 1 ? "s" : ""}`} onDelete={() => goToLevel(0)} variant="outlined" />}
        </Stack>

        {!ready && <Alert severity="info">Choose both dates of the custom comparison range.</Alert>}
        <Warnings warnings={meta?.warnings} />

        <StatStrip testId="comparison-summary">
          <Stat label={`Previous · ${meta ? periodText(meta.comparison_period) : "…"}`} value={d ? money(d.totals.previous, currency) : "…"} sub={meta?.comparison_period?.label} testId="cmp-previous" />
          <Stat label={`Current · ${meta ? periodText(meta.period) : "…"}`} value={d ? money(d.totals.current, currency) : "…"} sub={meta?.period.is_incomplete ? `Incomplete: ${meta.period.days} day(s) of data` : meta?.period.label} testId="cmp-current" />
          <Stat label="Net change" value={d ? <DeltaText value={d.totals.diff} currency={currency} /> : "…"} sub={d ? (d.totals.significance === "normal" ? "Within normal variation" : d.totals.significance === "notable_increase" ? "Notable increase" : "Notable decrease") : undefined} testId="cmp-diff" />
          <Stat label="Change %" value={d ? <DeltaText value={d.totals.pct} kind="pct" /> : "…"} testId="cmp-pct" />
          <Stat label="Gross increase" value={summary ? money(summary.gross_increase, currency) : "…"} sub={summary ? `${summary.increased_count} increased · ${summary.new_count} new` : undefined} testId="cmp-gross-increase" />
          <Stat label="Gross decrease" value={summary ? money(summary.gross_decrease, currency) : "…"} sub={summary ? `${summary.decreased_count} decreased · ${summary.removed_count} removed` : undefined} testId="cmp-gross-decrease" />
        </StatStrip>

        {q.error ? (
          <Paper variant="outlined">
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          </Paper>
        ) : (
          <>
            <Section
              title={`Cost change waterfall · ${d?.group_by_label ?? ""}`}
              subtitle="Previous total → largest contributors (by absolute change) → current total. Axis does not start at zero. Click a bar to drill down."
              testId="comparison-waterfall"
              table={d ? <DataTable data={d.waterfall.steps} columns={stepCols} storageKey="cmp-steps" getRowId={(r) => r.key} testId="waterfall-steps-table" /> : undefined}
            >
              {!wfOption ? <ChartSkeleton height={340} /> : d && d.groups.length === 0 ? <EmptyState message="No cost in either period for this scope." /> : <EChart option={wfOption} height={360} ariaLabel="Cost change waterfall" onClick={onChartClick} testId="echart-comparison-waterfall" />}
              {d && (
                <Typography variant="caption" sx={{ display: "block", mt: 0.5 }} data-testid="comparison-reconciliation">
                  {money(d.waterfall.previous_total, currency)} {d.waterfall.net_change >= 0 ? "+" : "−"} {money(Math.abs(d.waterfall.net_change), currency)} ({pct(d.waterfall.pct_change)}) = {money(d.waterfall.current_total, currency)} ·{" "}
                  {d.waterfall.reconciled ? "Reconciled exactly." : `Reconciliation difference ${money(d.waterfall.reconciliation_difference, currency)}`}
                </Typography>
              )}
            </Section>

            <Paper variant="outlined" data-testid="contribution-table">
              <DataTable
                data={d?.groups ?? []}
                columns={columns}
                loading={q.isFetching}
                onRowClick={drillInto}
                getRowId={(r) => r.key || "__none__"}
                storageKey={`cmp-${s.group}`}
                defaultHidden={["previous_daily_avg", "current_records", "current_daily_avg"]}
                clientPageSize={50}
                toolbar={
                  <Typography variant="body2" color="text.secondary">
                    {d ? `${d.group_count.toLocaleString()} ${d.group_by_label.toLowerCase()} rows · sorted by ${SORTS.find((x) => x.value === s.sort)?.label.toLowerCase()}` : "Loading…"}
                    {d && (HIERARCHY[d.group_by] ? ` · click a row to drill into ${DIM_LABEL[HIERARCHY[d.group_by] as string]}` : " · click a row to see its billing records")}
                  </Typography>
                }
                testId="contribution-grid"
              />
            </Paper>
          </>
        )}

        <Accordion disableGutters expanded={s.records === "1"} onChange={(_, open) => set({ records: open ? "1" : "" })} sx={{ border: 1, borderColor: "divider", "&:before": { display: "none" } }} data-testid="records-section">
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Box>
              <Typography variant="h3">Billing records for this scope</Typography>
              <Typography variant="caption">Exact ingested rows behind the comparison (both periods), filtered by the current drill path.</Typography>
            </Box>
          </AccordionSummary>
          <AccordionDetails sx={{ p: 0 }}>{s.records === "1" && <RecordsTable path="/costs/records" params={{ ...apiParams, ...drillParams(drill), comparison: s.basis, compare_start_date: params.compare_start_date, compare_end_date: params.compare_end_date, include_comparison: true }} testId="comparison-records" />}</AccordionDetails>
        </Accordion>
      </Stack>
    </Box>
  );
}
