"use client";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { Box, Button, Chip, Stack, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";
import EChart, { type EChartsOption } from "@/charts/EChart";
import { DeltaText, MoneyText } from "@/components/common/Delta";
import { ExportMenu } from "@/components/common/ExportMenu";
import { PageHeader } from "@/components/common/PageHeader";
import { Section } from "@/components/common/Section";
import { ChartSkeleton, ErrorState, Warnings } from "@/components/common/States";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { compactMoney, escapeHtml, money, pct, periodText } from "@/lib/format";
import type { ReportMeta } from "@/lib/types";
import { useApi } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { categorical, fontStack, ink, otherColor, surface } from "@/styles/tokens";

export interface AppRow {
  key: string;
  application_id: number | null;
  name: string;
  is_shared: boolean;
  is_unallocated: boolean;
  production: number;
  non_production: number;
  other_environments: number;
  current: number;
  previous: number | null;
  diff: number | null;
  pct: number | null;
  budget: number | null;
  budget_name: string | null;
  month_to_date: number;
  run_rate: number;
  forecast: number;
  expected_variance: number | null;
  budget_utilization_pct: number | null;
  ytd_actual: number;
  ytd_previous_year: number;
  ytd_growth_pct: number | null;
  change_30d: number | null;
  change_30d_pct: number | null;
  potential_savings: number;
  open_anomalies: number;
}

// Environment-group colours are fixed by identity (slot order), never by rank.
const ENV_COLORS = { production: categorical[0], non_production: categorical[1], other: otherColor };

function stackedOption(rows: AppRow[], currency: string): EChartsOption {
  const labels = rows.map((r) => r.name);
  const mk = (name: string, key: "production" | "non_production" | "other_environments", color: string, last: boolean) => ({
    name,
    type: "bar",
    stack: "env",
    barMaxWidth: 24,
    data: rows.map((r) => r[key]),
    itemStyle: { color, borderColor: surface.card, borderWidth: 1, borderRadius: last ? [4, 4, 0, 0] : 0 },
    emphasis: { focus: "series" },
  });
  return {
    textStyle: { fontFamily: fontStack },
    legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, textStyle: { color: ink.secondary, fontSize: 11.5 } },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(15,108,189,0.06)" } },
      backgroundColor: "#fff",
      borderColor: surface.border,
      textStyle: { color: ink.primary, fontSize: 12 },
      formatter: (ps: { dataIndex: number }[]) => {
        const r = rows[ps[0].dataIndex];
        return (
          `<b>${escapeHtml(r.name)}</b><br/>Production: ${money(r.production, currency)}<br/>Non-Production: ${money(r.non_production, currency)}` +
          (r.other_environments ? `<br/>Shared / unallocated: ${money(r.other_environments, currency)}` : "") +
          `<br/><b>Total: ${money(r.current, currency)}</b>`
        );
      },
    },
    xAxis: { type: "category", data: labels, axisLabel: { color: ink.axis, fontSize: 11 }, axisTick: { show: false }, axisLine: { lineStyle: { color: ink.baseline } } },
    yAxis: { type: "value", axisLabel: { color: ink.axis, fontSize: 11, formatter: (v: number) => compactMoney(v, currency) }, splitLine: { lineStyle: { color: ink.grid } } },
    series: [
      mk("Production", "production", ENV_COLORS.production, false),
      mk("Non-Production", "non_production", ENV_COLORS.non_production, false),
      mk("Shared / unallocated", "other_environments", ENV_COLORS.other, true),
    ],
  };
}

export default function ApplicationsPage() {
  const { apiParams } = useGlobalFilters();
  const link = useLinkWithFilters();
  const router = useRouter();
  const q = useApi<{ data: AppRow[]; meta: ReportMeta & { month?: string[] } }>("/applications", apiParams);
  const rows = useMemo(() => q.data?.data ?? [], [q.data]);
  const meta = q.data?.meta;
  const currency = meta?.currency ?? "USD";
  const hasCmp = !!meta?.comparison_period;
  const option = useMemo(() => (rows.length ? stackedOption(rows, currency) : null), [rows, currency]);

  const columns = useMemo<ColumnDef<AppRow, unknown>[]>(
    () => [
      {
        id: "name",
        accessorKey: "name",
        header: "Application",
        size: 210,
        enableHiding: false,
        cell: ({ row }) => (
          <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
            <Typography variant="body2" noWrap sx={{ fontWeight: 600, color: row.original.application_id ? "primary.main" : "text.primary" }}>
              {row.original.name}
            </Typography>
            {row.original.is_shared && <Chip label="Shared" size="small" variant="outlined" color="info" />}
            {row.original.is_unallocated && <Chip label="Unallocated" size="small" variant="outlined" color="warning" />}
          </Stack>
        ),
      },
      { accessorKey: "production", header: "Production", size: 120, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      { accessorKey: "non_production", header: "Non-Production", size: 145, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      ...(hasCmp
        ? ([{ accessorKey: "previous", header: "Previous actual", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> }] as ColumnDef<AppRow, unknown>[])
        : []),
      { accessorKey: "current", header: "Current actual", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} bold /> },
      ...(hasCmp
        ? ([{ accessorKey: "diff", header: "Change", size: 120, meta: { numeric: true }, cell: ({ row }) => <DeltaText value={row.original.diff} currency={currency} /> }] as ColumnDef<AppRow, unknown>[])
        : []),
      { accessorKey: "budget", header: "Budget (month)", size: 145, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number | null} currency={currency} /> },
      { accessorKey: "run_rate", header: "Run rate", size: 120, meta: { numeric: true, label: "Run rate (month)" }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      { accessorKey: "forecast", header: "Forecast", size: 120, meta: { numeric: true, label: "Monthly forecast" }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      { accessorKey: "expected_variance", header: "Expected variance", size: 150, meta: { numeric: true }, cell: ({ row }) => <DeltaText value={row.original.expected_variance} currency={currency} /> },
      { accessorKey: "ytd_actual", header: "YTD actual", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      { accessorKey: "ytd_growth_pct", header: "YTD growth", size: 110, meta: { numeric: true, label: "YTD growth vs last year" }, cell: ({ row }) => <DeltaText value={row.original.ytd_growth_pct} kind="pct" /> },
      { accessorKey: "change_30d", header: "30-day change", size: 130, meta: { numeric: true }, cell: ({ row }) => <DeltaText value={row.original.change_30d} currency={currency} /> },
      { accessorKey: "potential_savings", header: "Potential savings", size: 150, meta: { numeric: true, label: "Potential savings (estimated)" }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      { accessorKey: "open_anomalies", header: "Open anomalies", size: 130, meta: { numeric: true }, cell: ({ getValue }) => (getValue() as number) || "—" },
      { accessorKey: "budget_utilization_pct", header: "Budget used", size: 110, meta: { numeric: true, label: "Budget utilisation (month-to-date)" }, cell: ({ getValue }) => pct(getValue() as number | null, { sign: false }) },
    ],
    [currency, hasCmp],
  );

  const totals = useMemo(() => rows.reduce((t, r) => ({ current: t.current + r.current, prod: t.prod + r.production, np: t.np + r.non_production, other: t.other + r.other_environments }), { current: 0, prod: 0, np: 0, other: 0 }), [rows]);

  return (
    <Box data-testid="applications-page">
      <PageHeader
        title="Application Cost Allocation"
        subtitle={meta ? `${periodText(meta.period)}${hasCmp ? ` vs ${periodText(meta.comparison_period)}` : ""} · ${currency} · ${meta.cost_type === "actual" ? "Actual" : "Amortized"} cost. Run rate, forecast and budget are for the current month.` : "Expenditure by application across production and non-production subscriptions"}
        actions={
          <>
            <ExportMenu params={{ ...apiParams, group_by: "application" }} view="explorer" />
            <Button variant="outlined" color="inherit" endIcon={<OpenInNewIcon fontSize="small" />} component={Link} href={link("/explorer", { group: "application", chart: "grouped" })}>
              Explore by application
            </Button>
          </>
        }
      />
      <Stack spacing={2}>
        <Warnings warnings={meta?.warnings} />
        <Section
          title="Production vs Non-Production by application"
          subtitle={rows.length ? `Total ${money(totals.current, currency)} · Production ${pct((totals.prod / (totals.current || 1)) * 100, { sign: false })} · Non-Production ${pct((totals.np / (totals.current || 1)) * 100, { sign: false })} · Shared/unallocated ${pct((totals.other / (totals.current || 1)) * 100, { sign: false })}` : " "}
          testId="applications-chart"
        >
          {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : option ? <EChart option={option} height={300} ariaLabel="Application cost split by production and non-production" onClick={(p) => { const r = rows.find((x) => x.name === p.name); if (r?.application_id) router.push(link(`/applications/${r.application_id}`)); }} /> : <ChartSkeleton height={300} />}
        </Section>
        <Section title="Application summary" subtitle="Shared and unallocated charges are shown separately and are never assigned to an application. Click an application for its drill-down." noPadding>
          <DataTable
            data={rows}
            columns={columns}
            loading={q.isFetching}
            error={q.error ? (q.error as Error).message : null}
            onRowClick={(r) => r.application_id && router.push(link(`/applications/${r.application_id}`))}
            getRowId={(r) => r.key}
            storageKey="applications-summary"
            defaultHidden={["budget_utilization_pct"]}
            testId="applications-table"
          />
        </Section>
      </Stack>
    </Box>
  );
}
