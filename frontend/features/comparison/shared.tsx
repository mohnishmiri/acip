"use client";
/**
 * Helpers shared by the analysis pages (comparison, anomalies, resources, investigation):
 * summary strip, drill breadcrumb, billing-record table, meter decomposition panels and
 * small chart builders. Tooltip text is always HTML-escaped.
 */
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import NavigateNextIcon from "@mui/icons-material/NavigateNext";
import { Box, Breadcrumbs, Button, Divider, Link as MuiLink, List, ListItem, ListItemIcon, ListItemText, Paper, Stack, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import { useRouter } from "next/navigation";
import { type ReactNode, useMemo, useState } from "react";
import EChart, { type EChartsOption } from "@/charts/EChart";
import { DeltaText, MoneyText } from "@/components/common/Delta";
import { Section } from "@/components/common/Section";
import { StatusChip } from "@/components/common/StatusChip";
import { ChartSkeleton, EmptyState, ErrorState } from "@/components/common/States";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import type { Params } from "@/lib/api";
import { DIM_LABEL, type DrillStep, resourceIdFor } from "@/lib/drill";
import { bucketLabel, compactMoney, escapeHtml, money, num, pct, shortDate } from "@/lib/format";
import type { ReportMeta } from "@/lib/types";
import { useApi, useFilterOptions } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { brand, fontStack, ink, polarity, previousColor, surface } from "@/styles/tokens";

// ----------------------------------------------------------------------------- strip --
export function Stat({ label, value, sub, testId }: { label: ReactNode; value: ReactNode; sub?: ReactNode; testId?: string }) {
  return (
    <Box sx={{ px: 2, py: 1, minWidth: 130 }} data-testid={testId}>
      <Typography variant="caption" component="div" noWrap>
        {label}
      </Typography>
      <Typography component="div" sx={{ fontSize: 17, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </Typography>
      {sub && (
        <Typography variant="caption" component="div" noWrap>
          {sub}
        </Typography>
      )}
    </Box>
  );
}

export function StatStrip({ children, testId }: { children: ReactNode; testId?: string }) {
  const items = (Array.isArray(children) ? children : [children]).filter(Boolean);
  return (
    <Paper variant="outlined" sx={{ display: "flex", flexWrap: "wrap", alignItems: "stretch" }} data-testid={testId}>
      {items.map((c, i) => (
        <Box key={i} sx={{ display: "flex" }}>
          {i > 0 && <Divider orientation="vertical" flexItem />}
          {c}
        </Box>
      ))}
    </Paper>
  );
}

// ------------------------------------------------------------------------ breadcrumb --
export function DrillBreadcrumb({ drill, groupLabel, onLevel }: { drill: DrillStep[]; groupLabel?: string; onLevel: (n: number) => void }) {
  const { filters } = useGlobalFilters();
  const opts = useFilterOptions().data;
  const appName = filters.app
    ? (opts?.applications.find((a) => String(a.id) === filters.app)?.name ?? (filters.app === "shared" ? "Shared Services" : filters.app === "unallocated" ? "Unallocated" : filters.app))
    : "All Applications";
  const envName = filters.env ? (opts?.environment_groups.find((e) => e.code === filters.env)?.name ?? filters.env) : null;
  const subName = filters.sub ? (opts?.subscriptions.find((x) => x.subscription_id === filters.sub)?.subscription_name ?? filters.sub) : null;
  return (
    <Stack direction="row" alignItems="center" spacing={1} sx={{ minHeight: 32 }}>
      {drill.length > 0 && (
        <Button size="small" startIcon={<ArrowBackIcon fontSize="small" />} onClick={() => onLevel(drill.length - 1)} data-testid="drill-back">
          Back
        </Button>
      )}
      <Breadcrumbs separator={<NavigateNextIcon sx={{ fontSize: 16 }} />} aria-label="Drill-down path" data-testid="breadcrumb">
        <MuiLink component="button" underline="hover" color={drill.length ? "primary" : "text.primary"} onClick={() => onLevel(0)} sx={{ fontSize: 13, fontWeight: 600 }}>
          {appName}
        </MuiLink>
        {envName && <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{envName}</Typography>}
        {subName && <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{subName}</Typography>}
        {drill.map((step, i) => (
          <MuiLink key={`${step.dim}-${i}`} component="button" underline="hover" color={i === drill.length - 1 ? "text.primary" : "primary"} onClick={() => onLevel(i + 1)} sx={{ fontSize: 13, fontWeight: 600 }} title={DIM_LABEL[step.dim]}>
            {step.label}
          </MuiLink>
        ))}
        {groupLabel && <Typography sx={{ fontSize: 13, color: "text.secondary" }}>by {groupLabel}</Typography>}
      </Breadcrumbs>
    </Stack>
  );
}

// ---------------------------------------------------------------------------- records --
export interface BillingRecord {
  id: number;
  usage_date: string;
  period: "current" | "comparison";
  subscription_name: string;
  resource_name: string | null;
  resource_group: string | null;
  resource_type: string | null;
  region: string | null;
  service_category: string;
  meter_category: string | null;
  meter_subcategory: string | null;
  meter_name: string | null;
  sku: string | null;
  quantity: number | null;
  unit_of_measure: string | null;
  effective_price: number | null;
  cost: number;
  billing_currency: string;
  charge_type: string | null;
  pricing_model: string | null;
  benefit_name: string | null;
  export_run_id: number | null;
  ingestion_file_id: number | null;
  source_row_number: number | null;
}

export function RecordsTable({ path, params, testId = "records-table", maxHeight = 460 }: { path: string; params: Params; testId?: string; maxHeight?: number }) {
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(50);
  const q = useApi<{ data: BillingRecord[]; meta: ReportMeta }>(path, { ...params, page, page_size: size });
  const currency = q.data?.meta.currency ?? "USD";
  const cols = useMemo<ColumnDef<BillingRecord, unknown>[]>(
    () => [
      { accessorKey: "usage_date", header: "Date", size: 100, enableSorting: false, cell: ({ getValue }) => shortDate(getValue() as string) },
      { accessorKey: "period", header: "Period", size: 105, enableSorting: false, cell: ({ getValue }) => <StatusChip value={getValue() as string} label={getValue() === "current" ? "Current" : "Comparison"} tone={getValue() === "current" ? "info" : "neutral"} /> },
      { accessorKey: "resource_name", header: "Resource", size: 190, enableSorting: false, cell: ({ getValue }) => (getValue() as string) ?? "(non-resource charge)" },
      { accessorKey: "meter_category", header: "Meter category", size: 140, enableSorting: false },
      { accessorKey: "meter_subcategory", header: "Meter subcategory", size: 180, enableSorting: false, meta: { label: "Meter subcategory" } },
      { accessorKey: "meter_name", header: "Meter", size: 170, enableSorting: false },
      { accessorKey: "sku", header: "SKU", size: 140, enableSorting: false },
      { accessorKey: "quantity", header: "Quantity", size: 110, enableSorting: false, meta: { numeric: true }, cell: ({ getValue }) => num(getValue() as number | null, 4) },
      { accessorKey: "unit_of_measure", header: "Unit", size: 100, enableSorting: false },
      { accessorKey: "effective_price", header: "Effective price", size: 120, enableSorting: false, meta: { numeric: true }, cell: ({ getValue }) => num(getValue() as number | null, 6) },
      { accessorKey: "cost", header: "Cost", size: 120, enableSorting: false, meta: { numeric: true }, cell: ({ row }) => <MoneyText value={row.original.cost} currency={row.original.billing_currency || currency} bold /> },
      { accessorKey: "charge_type", header: "Charge type", size: 110, enableSorting: false },
      { accessorKey: "pricing_model", header: "Pricing model", size: 120, enableSorting: false },
      { accessorKey: "benefit_name", header: "Benefit", size: 180, enableSorting: false, meta: { label: "Reservation / savings plan" } },
      { accessorKey: "subscription_name", header: "Subscription", size: 190, enableSorting: false },
      { accessorKey: "resource_group", header: "Resource group", size: 170, enableSorting: false },
      { accessorKey: "region", header: "Region", size: 100, enableSorting: false },
      { accessorKey: "service_category", header: "Service", size: 160, enableSorting: false },
      { accessorKey: "export_run_id", header: "Export run", size: 100, enableSorting: false, meta: { numeric: true, label: "Source export run" } },
      { accessorKey: "ingestion_file_id", header: "Source file", size: 100, enableSorting: false, meta: { numeric: true } },
      { accessorKey: "source_row_number", header: "Row", size: 80, enableSorting: false, meta: { numeric: true, label: "Source row number" } },
    ],
    [currency],
  );
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <DataTable
      data={q.data?.data ?? []}
      columns={cols}
      loading={q.isFetching}
      getRowId={(r) => String(r.id)}
      serverPaging={{ page, pageSize: size, total: q.data?.meta.total ?? 0, onChange: (p, s) => { setPage(p); setSize(s); } }}
      storageKey={`records-${testId}`}
      defaultHidden={["meter_subcategory", "benefit_name", "resource_group", "region", "service_category", "export_run_id", "ingestion_file_id", "source_row_number", "subscription_name"]}
      maxHeight={maxHeight}
      emptyMessage="No billing records for this scope and period."
      toolbar={
        <Typography variant="body2" color="text.secondary">
          {q.data ? `${(q.data.meta.total ?? 0).toLocaleString()} billing records (exact rows as ingested; each traceable to its source export file and row)` : "Loading records…"}
        </Typography>
      }
      testId={testId}
    />
  );
}

// ---------------------------------------------------------------------- decomposition --
export interface Effect {
  key: string;
  label: string;
  value: number;
  share_of_change: number | null;
}
export interface MeterRowOut {
  meter_key: string;
  meter_category: string | null;
  meter_subcategory: string | null;
  meter_name: string | null;
  unit: string | null;
  charge_type: string | null;
  pricing_model: string | null;
  sku: string | null;
  status: string;
  previous_quantity: number | null;
  current_quantity: number | null;
  quantity_diff: number | null;
  quantity_pct: number | null;
  previous_cost: number;
  current_cost: number;
  difference: number;
  pct_change: number | null;
  previous_unit_price: number | null;
  current_unit_price: number | null;
  unit_price_pct: number | null;
  volume_effect: number;
  price_effect: number;
  other_effect: number;
  resource_count: number;
}
export interface ResourceChange {
  resource_key: string;
  resource_name: string;
  status: string;
  previous_cost: number;
  current_cost: number;
  difference: number;
  pct_change: number | null;
}
export interface Decomposition {
  previous_total: number;
  current_total: number;
  difference: number;
  pct_change: number | null;
  reconciled: boolean;
  effects: Effect[];
  meters: MeterRowOut[];
  resources: ResourceChange[];
  confirmed_facts: { type: string; text: string; impact?: number | null }[];
  hypotheses: { type: string; text: string }[];
}

const tooltip = {
  backgroundColor: "#ffffff",
  borderColor: surface.border,
  borderWidth: 1,
  padding: [8, 10],
  textStyle: { color: ink.primary, fontSize: 12, fontFamily: fontStack },
  extraCssText: "box-shadow: 0 4px 14px rgba(16,24,40,0.10); border-radius: 6px;",
  confine: true,
};

export function effectsOption(effects: Effect[], currency: string): EChartsOption {
  const rows = [...effects].sort((a, b) => Math.abs(a.value) - Math.abs(b.value));
  return {
    textStyle: { fontFamily: fontStack },
    grid: { left: 20, right: 64, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      ...tooltip,
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(15,108,189,0.06)" } },
      formatter: (ps: { dataIndex: number }[]) => {
        const e = rows[ps[0].dataIndex];
        return `<b>${escapeHtml(e.label)}</b><br/>${money(e.value, currency, { sign: true })}${e.share_of_change !== null ? `<br/><span style="color:${ink.muted}">${pct(e.share_of_change, { sign: false })} of net change</span>` : ""}`;
      },
    },
    xAxis: { type: "value", axisLabel: { color: ink.axis, fontSize: 11, formatter: (v: number) => compactMoney(v, currency) }, splitLine: { lineStyle: { color: ink.grid } } },
    yAxis: { type: "category", data: rows.map((r) => r.label), axisLabel: { color: ink.secondary, fontSize: 11, width: 210, overflow: "truncate" }, axisTick: { show: false }, axisLine: { lineStyle: { color: ink.baseline } } },
    series: [
      {
        type: "bar",
        barMaxWidth: 18,
        data: rows.map((r) => ({ value: r.value, itemStyle: { color: r.value >= 0 ? polarity.increase : polarity.decrease, borderRadius: r.value >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4] } })),
        label: { show: true, position: "right", color: ink.secondary, fontSize: 11, formatter: (p: { value: number }) => `${p.value >= 0 ? "+" : ""}${compactMoney(p.value, currency)}` },
      },
    ],
  };
}

export function FactsAndHypotheses({ facts, hypotheses, note }: { facts: Decomposition["confirmed_facts"]; hypotheses: Decomposition["hypotheses"]; note?: string }) {
  return (
    <Stack direction={{ xs: "column", lg: "row" }} spacing={2} alignItems="stretch">
      <Paper variant="outlined" sx={{ flex: 1, borderLeft: `3px solid #0ca30c` }} data-testid="confirmed-facts">
        <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
          <Typography variant="h3">Confirmed from billing data</Typography>
          <Typography variant="caption">Calculated directly from ingested billing records.</Typography>
        </Box>
        {facts.length ? (
          <List dense>
            {facts.map((f, i) => (
              <ListItem key={i} alignItems="flex-start">
                <ListItemIcon sx={{ minWidth: 28, mt: 0.5 }}>
                  <CheckCircleOutlineIcon sx={{ fontSize: 17, color: "#006300" }} />
                </ListItemIcon>
                <ListItemText primary={f.text} slotProps={{ primary: { sx: { fontSize: 12.75 } } }} />
              </ListItem>
            ))}
          </List>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
            No material changes found in this scope.
          </Typography>
        )}
      </Paper>
      <Paper variant="outlined" sx={{ flex: 1, borderLeft: `3px solid #c9ced6`, bgcolor: surface.subtle }} data-testid="hypotheses">
        <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
          <Typography variant="h3">Possible explanations (unverified)</Typography>
          <Typography variant="caption">{note ?? "Billing data cannot prove these. Verify with Activity Log, Resource Graph or Azure Monitor before acting."}</Typography>
        </Box>
        {hypotheses.length ? (
          <List dense>
            {hypotheses.map((h, i) => (
              <ListItem key={i} alignItems="flex-start">
                <ListItemIcon sx={{ minWidth: 28, mt: 0.5 }}>
                  <HelpOutlineIcon sx={{ fontSize: 17, color: ink.muted }} />
                </ListItemIcon>
                <ListItemText
                  primary={
                    <>
                      <Box component="span" sx={{ fontWeight: 600, color: ink.secondary }}>
                        Unverified hypothesis:{" "}
                      </Box>
                      {h.text}
                    </>
                  }
                  slotProps={{ primary: { sx: { fontSize: 12.75, color: ink.secondary } } }}
                />
              </ListItem>
            ))}
          </List>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
            No hypotheses generated.
          </Typography>
        )}
      </Paper>
    </Stack>
  );
}

export function meterColumns(currency: string): ColumnDef<MeterRowOut, unknown>[] {
  return [
    {
      id: "meter",
      header: "Meter",
      size: 260,
      enableHiding: false,
      accessorFn: (r) => [r.meter_category, r.meter_subcategory, r.meter_name].filter(Boolean).join(" / "),
      cell: ({ row }) => (
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2" noWrap sx={{ fontWeight: 600 }} title={row.original.meter_name ?? ""}>
            {row.original.meter_name ?? "(no meter)"}
          </Typography>
          <Typography variant="caption" noWrap component="div">
            {[row.original.meter_category, row.original.meter_subcategory].filter(Boolean).join(" / ")}
          </Typography>
        </Box>
      ),
    },
    { accessorKey: "status", header: "Status", size: 120, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
    { accessorKey: "previous_quantity", header: "Prev qty", size: 110, meta: { numeric: true, label: "Previous quantity" }, cell: ({ getValue }) => num(getValue() as number | null, 2) },
    { accessorKey: "current_quantity", header: "Current qty", size: 110, meta: { numeric: true, label: "Current quantity" }, cell: ({ getValue }) => num(getValue() as number | null, 2) },
    { accessorKey: "quantity_pct", header: "Qty %", size: 90, meta: { numeric: true, label: "Quantity change %" }, cell: ({ row }) => <DeltaText value={row.original.quantity_pct} kind="pct" status={row.original.status} muted /> },
    { accessorKey: "unit", header: "Unit", size: 100 },
    { accessorKey: "previous_cost", header: "Prev cost", size: 120, meta: { numeric: true, label: "Previous cost" }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
    { accessorKey: "current_cost", header: "Current cost", size: 120, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} bold /> },
    { accessorKey: "difference", header: "Difference", size: 120, meta: { numeric: true }, cell: ({ getValue }) => <DeltaText value={getValue() as number} currency={currency} /> },
    { accessorKey: "previous_unit_price", header: "Prev unit price", size: 120, meta: { numeric: true, label: "Previous effective unit price" }, cell: ({ getValue }) => num(getValue() as number | null, 6) },
    { accessorKey: "current_unit_price", header: "Unit price", size: 110, meta: { numeric: true, label: "Current effective unit price" }, cell: ({ getValue }) => num(getValue() as number | null, 6) },
    { accessorKey: "unit_price_pct", header: "Price %", size: 90, meta: { numeric: true, label: "Unit price change %" }, cell: ({ getValue }) => <DeltaText value={getValue() as number | null} kind="pct" muted /> },
    { accessorKey: "volume_effect", header: "Volume effect", size: 120, meta: { numeric: true }, cell: ({ getValue }) => <DeltaText value={getValue() as number} currency={currency} muted /> },
    { accessorKey: "price_effect", header: "Price effect", size: 120, meta: { numeric: true }, cell: ({ getValue }) => <DeltaText value={getValue() as number} currency={currency} muted /> },
    { accessorKey: "other_effect", header: "Other effect", size: 120, meta: { numeric: true, label: "New/removed/commitment/credit effects" }, cell: ({ getValue }) => <DeltaText value={getValue() as number} currency={currency} muted /> },
    { accessorKey: "charge_type", header: "Charge type", size: 110 },
    { accessorKey: "pricing_model", header: "Pricing model", size: 120 },
    { accessorKey: "sku", header: "SKU", size: 140 },
    { accessorKey: "resource_count", header: "Resources", size: 90, meta: { numeric: true } },
  ];
}

/** Effects + facts/hypotheses + meter table + contributing resources for a decomposition result. */
export function DecompositionPanels({ data, meta, loading, error, onRetry, showResources = true, testPrefix = "decomp" }: { data?: Decomposition; meta?: ReportMeta; loading?: boolean; error?: unknown; onRetry?: () => void; showResources?: boolean; testPrefix?: string }) {
  const router = useRouter();
  const link = useLinkWithFilters();
  const { apiParams } = useGlobalFilters();
  const currency = meta?.currency ?? "USD";
  const opt = useMemo(() => (data && data.effects.length ? effectsOption(data.effects, currency) : null), [data, currency]);
  const effCols = useMemo<ColumnDef<Effect, unknown>[]>(
    () => [
      { accessorKey: "label", header: "Effect", size: 280 },
      { accessorKey: "value", header: "Contribution", size: 140, meta: { numeric: true }, cell: ({ getValue }) => <DeltaText value={getValue() as number} currency={currency} /> },
      { accessorKey: "share_of_change", header: "Share of net change", size: 150, meta: { numeric: true }, cell: ({ getValue }) => pct(getValue() as number | null, { sign: false }) },
    ],
    [currency],
  );
  const mCols = useMemo(() => meterColumns(currency), [currency]);
  const rCols = useMemo<ColumnDef<ResourceChange, unknown>[]>(
    () => [
      { accessorKey: "resource_name", header: "Resource", size: 280, cell: ({ getValue }) => <Typography variant="body2" noWrap sx={{ fontWeight: 600, color: "primary.main" }}>{getValue() as string}</Typography> },
      { accessorKey: "status", header: "Status", size: 110, cell: ({ getValue }) => <StatusChip value={getValue() as string} label={getValue() === "existing" ? "Existing" : undefined} tone={getValue() === "existing" ? "neutral" : undefined} /> },
      { accessorKey: "previous_cost", header: "Previous", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      { accessorKey: "current_cost", header: "Current", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} bold /> },
      { accessorKey: "difference", header: "Difference", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <DeltaText value={getValue() as number} currency={currency} /> },
      { accessorKey: "pct_change", header: "Change %", size: 100, meta: { numeric: true }, cell: ({ row }) => <DeltaText value={row.original.pct_change} kind="pct" status={row.original.status} /> },
    ],
    [currency],
  );
  if (error) return <Paper variant="outlined"><ErrorState error={error} onRetry={onRetry} /></Paper>;
  if (!data) return <Paper variant="outlined" sx={{ p: 2 }}><ChartSkeleton height={220} /></Paper>;
  return (
    <Stack spacing={2} data-testid={`${testPrefix}-panels`}>
      <StatStrip testId={`${testPrefix}-summary`}>
        <Stat label={`Previous${meta?.comparison_period ? ` · ${shortDate(meta.comparison_period.start)} – ${shortDate(meta.comparison_period.end)}` : ""}`} value={money(data.previous_total, currency)} />
        <Stat label={`Current${meta ? ` · ${shortDate(meta.period.start)} – ${shortDate(meta.period.end)}` : ""}`} value={money(data.current_total, currency)} />
        <Stat label="Difference" value={<DeltaText value={data.difference} currency={currency} />} sub={data.pct_change !== null ? pct(data.pct_change) : undefined} />
        <Stat label="Reconciliation" value={data.reconciled ? "Exact" : "Check"} sub={data.reconciled ? "Effects sum to the net change" : "Effects do not sum to the change"} testId={`${testPrefix}-reconciled`} />
      </StatStrip>
      <Section
        title="What drove the change"
        subtitle="Net change split into mutually exclusive effects (usage volume, effective price, new/removed meters & resources, commitments, credits)"
        testId={`${testPrefix}-effects`}
        table={<DataTable data={data.effects} columns={effCols} storageKey={`${testPrefix}-effects`} />}
      >
        {loading && !opt ? <ChartSkeleton height={200} /> : opt ? <EChart option={opt} height={Math.max(140, data.effects.length * 38 + 30)} ariaLabel="Cost change effects" /> : <EmptyState title="No change" message="Costs are identical in both periods." />}
      </Section>
      <FactsAndHypotheses facts={data.confirmed_facts} hypotheses={data.hypotheses} note={meta?.evidence_note as string | undefined} />
      <Paper variant="outlined" data-testid={`${testPrefix}-meters`}>
        <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
          <Typography variant="h3">Meter-level comparison</Typography>
          <Typography variant="caption">Effective unit price = billed cost ÷ billed quantity (reflects discounts and commitments, not list price).</Typography>
        </Box>
        <DataTable data={data.meters} columns={mCols} storageKey={`${testPrefix}-meters`} defaultHidden={["previous_unit_price", "charge_type", "pricing_model", "sku", "resource_count", "other_effect"]} getRowId={(r) => `${r.meter_key}|${r.charge_type}|${r.pricing_model}`} />
      </Paper>
      {showResources && (
        <Paper variant="outlined" data-testid={`${testPrefix}-resources`}>
          <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
            <Typography variant="h3">Contributing resources</Typography>
            <Typography variant="caption">Click a resource to open its analysis.</Typography>
          </Box>
          <DataTable
            data={data.resources}
            columns={rCols}
            storageKey={`${testPrefix}-resources`}
            getRowId={(r) => r.resource_key || "__none__"}
            onRowClick={async (r) => {
              if (!r.resource_key) return;
              const id = await resourceIdFor(r.resource_key, apiParams);
              if (id) router.push(link(`/resources/${id}`));
            }}
          />
        </Paper>
      )}
    </Stack>
  );
}

// ------------------------------------------------------------------------ chart utils --
export function costSeriesOption(points: { label: string; value: number }[], currency: string, opts: { kind?: "bar" | "line"; markLine?: number | null; markLineLabel?: string; highlight?: [number, number] | null; name?: string } = {}): EChartsOption {
  const labels = points.map((p) => p.label);
  const kind = opts.kind ?? "line";
  const series: Record<string, unknown> = {
    name: opts.name ?? "Cost",
    type: kind,
    data: points.map((p) => p.value),
    barMaxWidth: 24,
    symbol: "circle",
    symbolSize: 6,
    showSymbol: points.length <= 45,
    lineStyle: { width: 2, color: brand.primary },
    itemStyle: kind === "bar" ? { color: brand.primary, borderRadius: [4, 4, 0, 0] } : { color: brand.primary, borderColor: surface.card, borderWidth: 2 },
    areaStyle: kind === "line" ? { color: brand.primary, opacity: 0.1 } : undefined,
  };
  if (opts.markLine !== null && opts.markLine !== undefined) {
    series.markLine = {
      silent: true,
      symbol: "none",
      lineStyle: { color: ink.secondary, width: 1.5, type: "solid" },
      label: { formatter: `${opts.markLineLabel ?? "Baseline"}\n${compactMoney(opts.markLine, currency)}`, color: ink.secondary, fontSize: 11, position: "end", lineHeight: 14 },
      data: [{ yAxis: opts.markLine }],
    };
  }
  if (opts.highlight) {
    series.markArea = { silent: true, itemStyle: { color: "rgba(227,73,72,0.07)" }, data: [[{ xAxis: labels[opts.highlight[0]] }, { xAxis: labels[opts.highlight[1]] }]] };
  }
  return {
    textStyle: { fontFamily: fontStack },
    grid: { left: 8, right: opts.markLine !== null && opts.markLine !== undefined ? 104 : 16, top: 20, bottom: 8, containLabel: true },
    tooltip: {
      ...tooltip,
      trigger: "axis",
      axisPointer: { type: kind === "bar" ? "shadow" : "line", lineStyle: { color: ink.baseline }, shadowStyle: { color: "rgba(15,108,189,0.06)" } },
      formatter: (ps: { dataIndex: number; value: number }[]) => `<b>${escapeHtml(labels[ps[0].dataIndex])}</b><br/>${escapeHtml(opts.name ?? "Cost")}: <b>${money(ps[0].value, currency)}</b>`,
    },
    xAxis: { type: "category", data: labels, boundaryGap: kind === "bar", axisLabel: { color: ink.axis, fontSize: 11, hideOverlap: true }, axisLine: { lineStyle: { color: ink.baseline } }, axisTick: { show: false } },
    yAxis: { type: "value", axisLabel: { color: ink.axis, fontSize: 11, formatter: (v: number) => compactMoney(v, currency) }, splitLine: { lineStyle: { color: ink.grid } } },
    series: [series],
  };
}

export function quantityOption(dates: string[], values: number[], unit: string, name: string): EChartsOption {
  const labels = dates.map((d) => bucketLabel(d, "daily"));
  return {
    textStyle: { fontFamily: fontStack },
    grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
    tooltip: {
      ...tooltip,
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: ink.baseline } },
      formatter: (ps: { dataIndex: number; value: number }[]) => `<b>${escapeHtml(labels[ps[0].dataIndex])}</b><br/>${escapeHtml(name)}: <b>${num(ps[0].value, 2)} ${escapeHtml(unit)}</b>`,
    },
    xAxis: { type: "category", data: labels, boundaryGap: false, axisLabel: { color: ink.axis, fontSize: 11, hideOverlap: true }, axisLine: { lineStyle: { color: ink.baseline } }, axisTick: { show: false } },
    yAxis: { type: "value", name: unit, nameTextStyle: { color: ink.axis, fontSize: 11, align: "left" }, axisLabel: { color: ink.axis, fontSize: 11 }, splitLine: { lineStyle: { color: ink.grid } } },
    series: [{ name, type: "line", data: values, symbol: "none", lineStyle: { width: 2, color: "#1baf7a" }, areaStyle: { color: "#1baf7a", opacity: 0.1 } }],
  };
}

export { previousColor };
