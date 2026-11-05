"use client";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import { Alert, Box, Button, Chip, Grid, IconButton, Paper, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import EChart, { type EChartsOption } from "@/charts/EChart";
import { DeltaText, MoneyText } from "@/components/common/Delta";
import { PageHeader } from "@/components/common/PageHeader";
import { Section } from "@/components/common/Section";
import { StatusChip } from "@/components/common/StatusChip";
import { ChartSkeleton, ErrorState, Warnings } from "@/components/common/States";
import { useGlobalFilters } from "@/hooks/useGlobalFilters";
import { useUrlState } from "@/hooks/useUrlState";
import { api } from "@/lib/api";
import { compactMoney, escapeHtml, longDate, money, pct, shortDate, titleCase } from "@/lib/format";
import type { ReportMeta } from "@/lib/types";
import { useApi } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { fontStack, ink, surface } from "@/styles/tokens";
import { ConfirmDialog, errorMessage, ToastProvider, useCan, useToast, UtilizationMeter } from "@/features/admin/ui";
import { BudgetForm, type BudgetLike } from "./BudgetForm";

interface BudgetRow extends BudgetLike {
  scope_label: string;
  period_start: string;
  period_end: string;
  as_of: string;
  actual: number;
  remaining: number;
  utilization_pct: number | null;
  forecast: number;
  forecast_method_label: string;
  forecast_variance: number | null;
  forecast_utilization_pct: number | null;
  daily_run_rate: number;
  elapsed_days: number;
  remaining_days: number;
  thresholds_crossed: number[];
  forecast_exceeds_budget: boolean;
  is_demo: boolean;
}

interface MethodResult {
  method: string;
  label: string;
  actual_to_date: number;
  projected_remaining: number;
  forecast_total: number;
  daily_rate: number;
  elapsed_days: number;
  remaining_days: number;
  notes: string[];
  projection: { date: string; value: number }[];
}
interface ForecastData {
  month: { start: string; end: string };
  selected_method: string;
  methods: Record<string, MethodResult>;
  actual_series: { date: string; value: number }[];
  annual: { actual_to_date: number; forecast_total: number; method: string };
  budget: { name: string; monthly_amount: number } | null;
  disclaimer: string;
}

const METHOD_EXPLAIN: Record<string, string> = {
  run_rate: "Month-to-date actual + (month-to-date daily average × remaining days).",
  recent: "Month-to-date actual + (average of the last 7 days × remaining days). Reacts faster to recent changes.",
  trend: "Month-to-date actual + a least-squares linear trend fitted to the last 60 days, projected day by day (floored at zero).",
};

function cumulativeOption(f: ForecastData, method: string, currency: string): EChartsOption {
  const days: string[] = [];
  const start = new Date(`${f.month.start}T00:00:00Z`);
  const end = new Date(`${f.month.end}T00:00:00Z`);
  for (let d = start; d <= end; d = new Date(d.getTime() + 86400000)) days.push(d.toISOString().slice(0, 10));
  const actualMap = new Map(f.actual_series.map((p) => [p.date, p.value]));
  const proj = new Map(f.methods[method]?.projection.map((p) => [p.date, p.value]) ?? []);
  let run = 0;
  const actual: (number | null)[] = [];
  const forecast: (number | null)[] = [];
  let lastActualIdx = -1;
  days.forEach((d, i) => {
    if (actualMap.has(d)) {
      run += actualMap.get(d) ?? 0;
      actual.push(run);
      forecast.push(null);
      lastActualIdx = i;
    } else {
      actual.push(null);
      if (proj.has(d)) {
        run += proj.get(d) ?? 0;
        forecast.push(run);
      } else forecast.push(null);
    }
  });
  if (lastActualIdx >= 0) forecast[lastActualIdx] = actual[lastActualIdx];
  const budget = f.budget?.monthly_amount ?? null;
  const labels = days.map((d) => shortDate(d));
  const series: unknown[] = [
    { name: "Cumulative actual", type: "line", symbol: "circle", symbolSize: 6, showSymbol: lastActualIdx < 3, lineStyle: { width: 2, color: "#0f6cbd" }, itemStyle: { color: "#0f6cbd", borderColor: "#fff", borderWidth: 2 }, areaStyle: { color: "#0f6cbd", opacity: 0.1 }, data: actual },
    { name: `Forecast (${f.methods[method]?.label ?? method})`, type: "line", symbol: "none", lineStyle: { width: 2, color: "#eb6834" }, itemStyle: { color: "#eb6834" }, data: forecast },
  ];
  if (budget !== null) series.push({ name: "Monthly budget", type: "line", symbol: "none", lineStyle: { width: 2, color: ink.secondary }, itemStyle: { color: ink.secondary }, data: days.map(() => budget) });
  return {
    textStyle: { fontFamily: fontStack },
    legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, textStyle: { color: ink.secondary, fontSize: 11.5 } },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: surface.border,
      textStyle: { color: ink.primary, fontSize: 12 },
      formatter: (ps: { dataIndex: number; seriesName: string; value: number | null }[]) =>
        `<b>${escapeHtml(labels[ps[0].dataIndex])}</b>` + ps.filter((p) => p.value !== null && p.value !== undefined).map((p) => `<br/>${escapeHtml(p.seriesName)}: <b>${money(p.value as number, currency)}</b>`).join(""),
    },
    xAxis: { type: "category", data: labels, boundaryGap: false, axisLabel: { color: ink.axis, fontSize: 11 }, axisTick: { show: false }, axisLine: { lineStyle: { color: ink.baseline } } },
    yAxis: { type: "value", axisLabel: { color: ink.axis, fontSize: 11, formatter: (v: number) => compactMoney(v, currency) }, splitLine: { lineStyle: { color: ink.grid } } },
    series,
  };
}

function BudgetsInner() {
  const { apiParams } = useGlobalFilters();
  const [local, setLocal] = useUrlState({ method: "" });
  const canManage = useCan("manage_budgets");
  const toast = useToast();
  const qc = useQueryClient();
  const budgets = useApi<{ data: BudgetRow[]; meta: { forecast_methods: Record<string, string> } }>("/budgets");
  const forecast = useApi<{ data: ForecastData; meta: ReportMeta }>("/forecasts", { ...apiParams, preset: "month_to_date", start_date: undefined, end_date: undefined, method: local.method || undefined });
  const [editing, setEditing] = useState<BudgetRow | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [deleting, setDeleting] = useState<BudgetRow | null>(null);
  const [busy, setBusy] = useState(false);

  const fd = forecast.data?.data;
  const currency = forecast.data?.meta.currency ?? "USD";
  const method = local.method || fd?.selected_method || "run_rate";
  const option = useMemo(() => (fd ? cumulativeOption(fd, method, currency) : null), [fd, method, currency]);
  const invalidate = () => qc.invalidateQueries({ predicate: (q) => typeof q.queryKey[0] === "string" && ["/budgets", "/dashboard", "/forecasts", "/applications"].some((p) => (q.queryKey[0] as string).startsWith(p)) });

  const columns = useMemo<ColumnDef<BudgetRow, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Budget",
        size: 220,
        enableHiding: false,
        cell: ({ row }) => (
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="body2" noWrap sx={{ fontWeight: 600 }} title={row.original.name}>
              {row.original.name}
            </Typography>
            <Typography variant="caption" noWrap component="div">
              {titleCase(row.original.scope_type)} · {row.original.scope_label}
            </Typography>
          </Box>
        ),
      },
      { id: "period", header: "Period", size: 125, accessorFn: (r) => r.period_start, cell: ({ row }) => <Box><Typography variant="body2">{titleCase(row.original.period_type)}</Typography><Typography variant="caption">{shortDate(row.original.period_start)} – {shortDate(row.original.period_end)}</Typography></Box> },
      { accessorKey: "amount", header: "Budget", size: 115, meta: { numeric: true }, cell: ({ row }) => <MoneyText value={row.original.amount} currency={row.original.currency} /> },
      { accessorKey: "actual", header: "Actual", size: 115, meta: { numeric: true }, cell: ({ row }) => <MoneyText value={row.original.actual} currency={row.original.currency} bold /> },
      {
        accessorKey: "utilization_pct",
        header: "Utilisation",
        size: 160,
        cell: ({ row }) => (
          <Stack direction="row" spacing={1} alignItems="center">
            <UtilizationMeter utilization={row.original.utilization_pct} forecastPct={row.original.forecast_utilization_pct} label={`${row.original.name} utilisation`} />
            <Typography variant="caption" sx={{ minWidth: 44, textAlign: "right", fontWeight: 600, color: "text.primary" }}>
              {pct(row.original.utilization_pct, { sign: false })}
            </Typography>
          </Stack>
        ),
      },
      { accessorKey: "remaining", header: "Remaining", size: 120, meta: { numeric: true }, cell: ({ row }) => <MoneyText value={row.original.remaining} currency={row.original.currency} /> },
      { accessorKey: "forecast", header: "Forecast", size: 115, meta: { numeric: true, label: "Forecast (projection)" }, cell: ({ row }) => <Tooltip title={row.original.forecast_method_label}><span><MoneyText value={row.original.forecast} currency={row.original.currency} /></span></Tooltip> },
      { accessorKey: "forecast_variance", header: "Fcst variance", size: 125, meta: { numeric: true, label: "Expected variance (forecast − budget)" }, cell: ({ row }) => <DeltaText value={row.original.forecast_variance} currency={row.original.currency} /> },
      { accessorKey: "daily_run_rate", header: "Daily run rate", size: 120, meta: { numeric: true }, cell: ({ row }) => <MoneyText value={row.original.daily_run_rate} currency={row.original.currency} /> },
      {
        id: "alerts",
        header: "Thresholds",
        size: 175,
        enableSorting: false,
        meta: { label: "Alert thresholds (filled = crossed)" },
        cell: ({ row }) => (
          <Stack direction="row" spacing={0.25} sx={{ overflow: "hidden" }}>
            {row.original.thresholds.map((t) => {
              const hit = row.original.thresholds_crossed.map(Number).includes(Number(t));
              return (
                <Chip
                  key={t}
                  label={`${Number(t)}%`}
                  size="small"
                  variant={hit ? "filled" : "outlined"}
                  color={hit ? (Number(t) >= 100 ? "error" : "warning") : "default"}
                  sx={{ height: 20, "& .MuiChip-label": { px: 0.6, fontSize: 10.5 } }}
                  title={hit ? "Crossed this period" : "Not crossed"}
                />
              );
            })}
          </Stack>
        ),
      },
      {
        id: "forecast_flag",
        header: "Forecast",
        size: 150,
        accessorFn: (r) => (r.forecast_exceeds_budget ? 1 : 0),
        meta: { label: "Forecast exceeds budget" },
        cell: ({ row }) => (row.original.forecast_exceeds_budget ? <StatusChip value="warning" label="Exceeds budget" tone="serious" /> : <StatusChip value="ok" label="Within budget" />),
      },
      { id: "enabled", header: "Enabled", size: 90, accessorFn: (r) => r.enabled, cell: ({ row }) => (row.original.enabled ? "Yes" : <StatusChip value="disabled" />) },
      {
        id: "actions",
        header: "",
        size: 84,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) =>
          canManage ? (
            <Stack direction="row">
              <Tooltip title="Edit">
                <IconButton aria-label={`Edit ${row.original.name}`} onClick={(e) => { e.stopPropagation(); setEditing(row.original); setFormOpen(true); }} data-testid={`budget-edit-${row.original.id}`}>
                  <EditOutlinedIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Delete">
                <IconButton aria-label={`Delete ${row.original.name}`} onClick={(e) => { e.stopPropagation(); setDeleting(row.original); }} data-testid={`budget-delete-${row.original.id}`}>
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          ) : null,
      },
    ],
    [canManage],
  );

  const rows = budgets.data?.data ?? [];
  const methods = fd ? Object.values(fd.methods) : [];
  const methodCols = useMemo<ColumnDef<MethodResult, unknown>[]>(
    () => [
      { accessorKey: "label", header: "Method", size: 260, cell: ({ row }) => <Typography variant="body2" sx={{ fontWeight: row.original.method === method ? 600 : 400 }}>{row.original.label}{row.original.method === method ? " (selected)" : ""}</Typography> },
      { accessorKey: "actual_to_date", header: "Actual to date", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      { accessorKey: "projected_remaining", header: "Projected remaining", size: 150, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      { accessorKey: "forecast_total", header: "Month-end forecast", size: 150, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} bold /> },
      { accessorKey: "daily_rate", header: "Daily rate", size: 120, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      { id: "days", header: "Days", size: 110, accessorFn: (r) => r.elapsed_days, cell: ({ row }) => `${row.original.elapsed_days} elapsed / ${row.original.remaining_days} left` },
      { id: "notes", header: "Notes", size: 260, accessorFn: (r) => r.notes.join(" "), cell: ({ getValue }) => (getValue() as string) || "—" },
    ],
    [currency, method],
  );

  return (
    <Box data-testid="budgets-page">
      <PageHeader
        title="Budget & Forecast"
        subtitle="Budgets by total, application, subscription, environment or resource group. Forecasts are projections from billed history and are never presented as actual charges."
        actions={
          canManage ? (
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => { setEditing(null); setFormOpen(true); }} data-testid="budget-new">
              New budget
            </Button>
          ) : (
            <Typography variant="caption">Your role can view budgets but not change them.</Typography>
          )
        }
      />
      <Stack spacing={2}>
        <Section title="Budgets" subtitle={rows.length ? `${rows.length} budgets · utilisation fill = actual, marker = forecast month/period-end` : " "} noPadding testId="budgets-table-section">
          <DataTable data={rows} columns={columns} loading={budgets.isFetching} error={budgets.error ? errorMessage(budgets.error) : null} getRowId={(r) => String(r.id)} storageKey="budgets" defaultHidden={["enabled", "daily_run_rate", "remaining", "forecast_flag"]} emptyMessage="No budgets configured." testId="budgets-table" />
        </Section>

        <Warnings warnings={forecast.data?.meta.warnings} />
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 8 }}>
            <Section
              title="Month-end forecast"
              subtitle={fd ? `${longDate(fd.month.start)} – ${longDate(fd.month.end)} · ${currency} · scope follows the global filters${fd.budget ? ` · budget: ${fd.budget.name}` : " · no matching budget for this scope"}` : " "}
              testId="forecast-panel"
              actions={
                <ToggleButtonGroup size="small" exclusive value={method} onChange={(_, v) => v && setLocal({ method: v })} aria-label="Forecast method" data-testid="forecast-method">
                  <ToggleButton value="run_rate">Run rate</ToggleButton>
                  <ToggleButton value="recent">Recent</ToggleButton>
                  <ToggleButton value="trend">Trend</ToggleButton>
                </ToggleButtonGroup>
              }
              table={<DataTable data={methods} columns={methodCols} storageKey="forecast-methods" />}
            >
              {forecast.error ? <ErrorState error={forecast.error} onRetry={() => forecast.refetch()} /> : option ? <EChart option={option} height={300} ariaLabel="Cumulative actual cost and forecast for the month" /> : <ChartSkeleton height={300} />}
              <Alert severity="info" variant="outlined" sx={{ mt: 1, bgcolor: "#fff" }}>
                <b>Methodology ({fd?.methods[method]?.label ?? method}):</b> {METHOD_EXPLAIN[method]} {fd?.disclaimer}
              </Alert>
            </Section>
          </Grid>
          <Grid size={{ xs: 12, lg: 4 }}>
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ p: 2 }} data-testid="forecast-summary">
                <Typography variant="subtitle2">Month-end forecast (projection)</Typography>
                <Typography sx={{ fontSize: 24, fontWeight: 600 }}>{fd ? money(fd.methods[method]?.forecast_total, currency) : "…"}</Typography>
                <Typography variant="caption" component="div">
                  Actual to date {fd ? money(fd.methods[method]?.actual_to_date, currency) : "…"} + projected {fd ? money(fd.methods[method]?.projected_remaining, currency) : "…"}
                </Typography>
                {fd?.budget && (
                  <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: (fd.methods[method]?.forecast_total ?? 0) > fd.budget.monthly_amount ? "#b42318" : "text.secondary" }}>
                    {(fd.methods[method]?.forecast_total ?? 0) > fd.budget.monthly_amount ? "Projected overspend" : "Projected headroom"} {money(Math.abs((fd.methods[method]?.forecast_total ?? 0) - fd.budget.monthly_amount), currency)} vs {money(fd.budget.monthly_amount, currency)} budget
                  </Typography>
                )}
                <Box sx={{ borderTop: `1px solid ${surface.border}`, my: 1.5 }} />
                <Typography variant="subtitle2">Annual forecast (projection)</Typography>
                <Typography sx={{ fontSize: 18, fontWeight: 600 }}>{fd ? money(fd.annual.forecast_total, currency) : "…"}</Typography>
                <Typography variant="caption" component="div">
                  Year-to-date actual {fd ? money(fd.annual.actual_to_date, currency) : "…"} · {fd?.annual.method}
                </Typography>
              </Paper>
              <Paper variant="outlined" sx={{ p: 2 }} data-testid="threshold-explanation">
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  How budget alerts work
                </Typography>
                <Typography variant="body2" component="div" sx={{ "& li": { mb: 0.5 } }}>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    <li>Each budget has thresholds (default 70%, 80%, 90%, 100%) of the period amount.</li>
                    <li>After every ingestion the worker evaluates utilisation; each crossed threshold raises one in-app notification per budget period (no repeats).</li>
                    <li>With &quot;forecast alert&quot; enabled, a notification is raised when the selected forecast method projects spend above the budget.</li>
                    <li>Budgets compare against one billing currency and one cost type (actual or amortized); nothing is converted or mixed.</li>
                  </ul>
                </Typography>
              </Paper>
            </Stack>
          </Grid>
        </Grid>
      </Stack>

      <BudgetForm
        open={formOpen}
        budget={editing}
        onClose={() => setFormOpen(false)}
        onSaved={(msg) => {
          setFormOpen(false);
          toast(msg);
          invalidate();
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        title="Delete budget"
        message={<>Delete <b>{deleting?.name}</b>? Alert history is kept; the budget will no longer be evaluated.</>}
        confirmLabel="Delete"
        danger
        busy={busy}
        testId="budget-delete-dialog"
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          if (!deleting) return;
          setBusy(true);
          try {
            await api(`/budgets/${deleting.id}`, { method: "DELETE" });
            toast("Budget deleted");
            invalidate();
          } catch (e) {
            toast(errorMessage(e), "error");
          } finally {
            setBusy(false);
            setDeleting(null);
          }
        }}
      />
    </Box>
  );
}

export default function BudgetsPage() {
  return (
    <ToastProvider>
      <BudgetsInner />
    </ToastProvider>
  );
}
