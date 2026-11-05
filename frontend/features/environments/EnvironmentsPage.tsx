"use client";
import { Alert, Box, Grid, Link as MuiLink, Paper, Stack, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";
import EChart from "@/charts/EChart";
import { donutOption, timeSeriesOption } from "@/charts/options";
import { DeltaText, MoneyText } from "@/components/common/Delta";
import { PageHeader } from "@/components/common/PageHeader";
import { Section } from "@/components/common/Section";
import { SeverityChip, StatusChip } from "@/components/common/StatusChip";
import { ChartSkeleton, ErrorState, Warnings } from "@/components/common/States";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { resourceIdFor } from "@/lib/drill";
import { bucketLabel, compactMoney, longDate, money, pct, periodText } from "@/lib/format";
import type { Envelope, ExplorerData, GroupItem } from "@/lib/types";
import { useApi, useExplorer, useFilterOptions } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { comparisonColumns } from "@/tables/columns";

interface AnomalyRow {
  id: number;
  anomaly_ref: string;
  title: string;
  severity: string;
  status: string;
  detection_date: string;
  absolute_increase: number;
  currency: string;
  application: string;
}
interface SavingsRow {
  id: number;
  title: string;
  status: string;
  estimated_monthly_savings: number | null;
  current_monthly_cost: number;
  currency: string;
  evidence_source: string;
  application: string;
}

function seriesRows(d: ExplorerData | undefined) {
  if (!d) return [];
  return d.series.buckets.map((b, i) => {
    const row: Record<string, number | string> = { bucket: b, total: d.series.total[i] };
    d.series.series.forEach((s) => (row[s.key] = s.values[i]));
    return row;
  });
}

function seriesColumns(d: ExplorerData | undefined, currency: string, granularity: string): ColumnDef<Record<string, number | string>, unknown>[] {
  if (!d) return [];
  return [
    { accessorKey: "bucket", header: "Period", size: 110, cell: ({ getValue }) => bucketLabel(getValue() as string, granularity) },
    ...d.series.series.map((s) => ({ accessorKey: s.key, header: s.label, size: 130, meta: { numeric: true }, cell: ({ getValue }: { getValue: () => unknown }) => <MoneyText value={getValue() as number} currency={currency} /> })),
    { accessorKey: "total", header: "Total", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} bold /> },
  ] as ColumnDef<Record<string, number | string>, unknown>[];
}

export default function EnvironmentsPage() {
  const { apiParams, filters } = useGlobalFilters();
  const link = useLinkWithFilters();
  const router = useRouter();
  const opts = useFilterOptions();
  const base = useMemo(() => ({ ...apiParams, environment: undefined }), [apiParams]);
  const cur = useExplorer({ ...base, group_by: "environment", granularity: "daily" });
  const monthly = useExplorer({ ...base, group_by: "environment", preset: "year_to_date", start_date: undefined, end_date: undefined, granularity: "monthly", comparison: "same_period_last_year" });
  const npResources = useApi<Envelope<GroupItem[]>>("/costs/contributors", { ...base, environment: ["non_production"], group_by: "resource", sort: "current_cost", page_size: 15 });
  const npMovers = useApi<Envelope<GroupItem[]>>("/costs/contributors", { ...base, environment: ["non_production"], group_by: "resource", sort: "abs_diff", page_size: 10 });
  const anomalies = useApi<{ data: AnomalyRow[]; meta: { total: number } }>("/anomalies", { environment: ["non_production"], status: ["open", "investigating", "acknowledged"], page_size: 10, application: filters.app && /^\d+$/.test(filters.app) ? [filters.app] : undefined });
  const savings = useApi<{ data: SavingsRow[]; meta: { open_estimated_monthly_savings: number } }>("/savings", { environment: ["non_production"], status: ["open", "investigating", "accepted"], application: filters.app && /^\d+$/.test(filters.app) ? [filters.app] : undefined });

  const d = cur.data?.data;
  const meta = cur.data?.meta;
  const currency = meta?.currency ?? "USD";
  const hasCmp = !!meta?.comparison_period;

  // Always list every environment (zero rows included) so absence is explicit.
  const envGroups = useMemo<GroupItem[]>(() => {
    if (!d) return [];
    const byKey = new Map(d.groups.map((g) => [g.key, g]));
    const all = opts.data?.environments ?? [];
    const rows = all.map((e) => byKey.get(e.code) ?? { key: e.code, label: e.name, current: 0, previous: 0, diff: 0, pct: null, status: "no_data", share_of_total: 0, current_records: 0, previous_records: 0 });
    for (const g of d.groups) if (!all.find((e) => e.code === g.key)) rows.push(g);
    return rows;
  }, [d, opts.data]);

  const prodShare = useMemo(() => {
    if (!d) return null;
    const envs = opts.data?.environments ?? [];
    const sum = (grp: string) => d.groups.filter((g) => envs.find((e) => e.code === g.key)?.group === grp).reduce((s, g) => s + g.current, 0);
    const prev = (grp: string) => d.groups.filter((g) => envs.find((e) => e.code === g.key)?.group === grp).reduce((s, g) => s + (g.previous ?? 0), 0);
    return { prod: sum("production"), np: sum("non_production"), shared: sum("shared"), un: sum("unallocated"), prodPrev: prev("production"), npPrev: prev("non_production"), total: d.totals.current };
  }, [d, opts.data]);

  const donut = useMemo(() => (d ? donutOption(d.groups, { currency, dimension: "environment" }) : null), [d, currency]);
  const daily = useMemo(() => (d ? timeSeriesOption(d.series, { currency, stacked: true, area: false, kind: "bar", byGroup: true, dimension: "environment", zoom: d.series.buckets.length > 31 }) : null), [d, currency]);
  const mo = monthly.data?.data;
  // The current month is usually partial; plotting it would show a false "cliff", so the chart
  // shows complete months only (the table below still lists the partial month, labelled).
  const partialMonth = useMemo(() => {
    const m = monthly.data?.meta;
    if (!m || !mo?.series.buckets.length) return null;
    const asOf = new Date(`${m.as_of}T00:00:00Z`);
    const monthEnd = new Date(Date.UTC(asOf.getUTCFullYear(), asOf.getUTCMonth() + 1, 0));
    return asOf.getTime() < monthEnd.getTime() ? { bucket: mo.series.buckets[mo.series.buckets.length - 1], days: asOf.getUTCDate() } : null;
  }, [monthly.data, mo]);
  const monthlyOpt = useMemo(() => {
    if (!mo) return null;
    const n = partialMonth ? mo.series.buckets.length - 1 : mo.series.buckets.length;
    const trimmed = {
      ...mo.series,
      buckets: mo.series.buckets.slice(0, n),
      total: mo.series.total.slice(0, n),
      series: mo.series.series.map((x) => ({ ...x, values: x.values.slice(0, n) })),
      previous_total: null,
      previous_buckets: null,
    };
    return timeSeriesOption(trimmed, { currency: monthly.data!.meta.currency, stacked: true, area: true, kind: "line", byGroup: true, dimension: "environment" });
  }, [mo, monthly.data, partialMonth]);

  const envCols = useMemo(() => comparisonColumns({ currency, hasComparison: hasCmp, labelHeader: "Environment" }), [currency, hasCmp]);
  const openResource = async (g: GroupItem) => {
    const id = g.key ? await resourceIdFor(g.key, base) : null;
    if (id) router.push(link(`/resources/${id}`));
  };
  const resCols = useMemo(() => comparisonColumns({ currency, hasComparison: hasCmp, labelHeader: "Non-Production resource", onLabelClick: openResource }), [currency, hasCmp]); // eslint-disable-line react-hooks/exhaustive-deps
  const anomalyCols = useMemo<ColumnDef<AnomalyRow, unknown>[]>(
    () => [
      { accessorKey: "severity", header: "Severity", size: 110, cell: ({ getValue }) => <SeverityChip severity={getValue() as string} /> },
      { accessorKey: "title", header: "Anomaly", size: 290, cell: ({ row }) => <MuiLink component={Link} href={link(`/anomalies/${row.original.id}`)} underline="hover" sx={{ fontWeight: 600 }}>{row.original.title}</MuiLink> },
      { accessorKey: "detection_date", header: "Detected", size: 110, cell: ({ getValue }) => longDate(getValue() as string) },
      { accessorKey: "absolute_increase", header: "Increase", size: 110, meta: { numeric: true }, cell: ({ row }) => <DeltaText value={row.original.absolute_increase} currency={row.original.currency} /> },
      { accessorKey: "status", header: "Status", size: 110, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
    ],
    [link],
  );
  const savingsCols = useMemo<ColumnDef<SavingsRow, unknown>[]>(
    () => [
      { accessorKey: "title", header: "Opportunity", size: 290, cell: ({ row }) => <Typography variant="body2" noWrap title={row.original.title} sx={{ fontWeight: 600 }}>{row.original.title}</Typography> },
      { accessorKey: "current_monthly_cost", header: "Monthly cost", size: 120, meta: { numeric: true }, cell: ({ row }) => <MoneyText value={row.original.current_monthly_cost} currency={row.original.currency} /> },
      { accessorKey: "estimated_monthly_savings", header: "Est. savings / mo", size: 130, meta: { numeric: true }, cell: ({ row }) => (row.original.estimated_monthly_savings === null ? <Typography variant="caption">Not estimated</Typography> : <MoneyText value={row.original.estimated_monthly_savings} currency={row.original.currency} />) },
      { accessorKey: "status", header: "Status", size: 110, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
    ],
    [],
  );

  return (
    <Box data-testid="environments-page">
      <PageHeader
        title="Production vs Non-Production"
        subtitle={meta ? `${periodText(meta.period)}${hasCmp ? ` vs ${periodText(meta.comparison_period)}` : ""} · ${currency} · environment classification from subscription mapping with configured resource-group / tag overrides` : " "}
      />
      <Stack spacing={2}>
        <Alert severity="info" variant="outlined" sx={{ bgcolor: "#fff" }} data-testid="nonprod-note">
          Non-Production expenditure is not assumed to be waste. Development, testing and UAT environments are necessary; this view highlights where Non-Production cost is significant so owners can confirm it is expected. Savings shown below are evidence-based estimates only.
          {filters.env ? " The global environment filter is ignored on this page so all environments can be compared." : ""}
        </Alert>
        <Warnings warnings={meta?.warnings} />

        {cur.error ? (
          <ErrorState error={cur.error} onRetry={() => cur.refetch()} />
        ) : (
          <Paper variant="outlined" sx={{ display: "flex", flexWrap: "wrap" }} data-testid="environment-summary">
            {[
              { label: "Production", v: prodShare?.prod, p: prodShare?.prodPrev },
              { label: "Non-Production (incl. dev / test / UAT)", v: prodShare?.np, p: prodShare?.npPrev },
              { label: "Shared Services", v: prodShare?.shared },
              { label: "Unallocated", v: prodShare?.un },
            ].map((x) => (
              <Box key={x.label} sx={{ px: 2, py: 1.25, minWidth: 190, flex: 1 }}>
                <Typography variant="caption" component="div">
                  {x.label}
                </Typography>
                <Typography sx={{ fontSize: 17, fontWeight: 600 }}>{x.v === undefined ? "…" : money(x.v, currency)}</Typography>
                <Typography variant="caption" component="div">
                  {prodShare && x.v !== undefined ? `${pct((x.v / (prodShare.total || 1)) * 100, { sign: false })} of total` : " "}
                  {hasCmp && x.p !== undefined && x.v !== undefined ? <> · <DeltaText value={x.v - x.p} currency={currency} /></> : null}
                </Typography>
              </Box>
            ))}
          </Paper>
        )}

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 5 }}>
            <Section title="Percentage distribution" subtitle="Share of current-period cost by environment" testId="environment-donut" table={<DataTable data={envGroups} columns={envCols} storageKey="env-distribution" defaultHidden={["previous_daily_avg", "current_records", "contribution_pct", "status"]} maxHeight={320} />}>
              {donut ? <EChart option={donut} height={280} ariaLabel="Cost distribution by environment" /> : <ChartSkeleton height={280} />}
            </Section>
          </Grid>
          <Grid size={{ xs: 12, lg: 7 }}>
            <Section title="Daily trend by environment" subtitle={meta ? periodText(meta.period) : " "} testId="environment-daily" table={<DataTable data={seriesRows(d)} columns={seriesColumns(d, currency, "daily")} storageKey="env-daily" maxHeight={320} />}>
              {daily ? <EChart option={daily} height={280} ariaLabel="Daily cost by environment" /> : <ChartSkeleton height={280} />}
            </Section>
          </Grid>
        </Grid>

        <Section
          title="Monthly trend by environment"
          subtitle={monthly.data ? `Year-to-date ${periodText(monthly.data.meta.period)} · total ${compactMoney(mo?.totals.current, monthly.data.meta.currency)} vs ${compactMoney(mo?.totals.previous, monthly.data.meta.currency)} same period last year${partialMonth ? ` · current month (${partialMonth.days} day${partialMonth.days > 1 ? "s" : ""}, partial) shown in the table only` : ""}` : " "}
          testId="environment-monthly"
          table={<DataTable data={seriesRows(mo)} columns={seriesColumns(mo, monthly.data?.meta.currency ?? currency, "monthly")} storageKey="env-monthly" maxHeight={320} />}
        >
          {monthly.error ? <ErrorState error={monthly.error} /> : monthlyOpt ? <EChart option={monthlyOpt} height={280} ariaLabel="Monthly cost by environment" /> : <ChartSkeleton height={280} />}
        </Section>

        <Section title="Environment comparison" subtitle={hasCmp ? `Current vs ${meta?.comparison_period?.label?.toLowerCase()}` : "Current period"} noPadding testId="environment-table">
          <DataTable data={envGroups} columns={envCols} storageKey="env-compare" defaultHidden={["current_records"]} loading={cur.isFetching} />
        </Section>

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, xl: 6 }}>
            <Section title="Top Non-Production resources" subtitle="Largest Non-Production cost (development, testing, UAT and non-production subscriptions)" noPadding testId="nonprod-top">
              <DataTable data={npResources.data?.data ?? []} columns={resCols} storageKey="env-np-top" defaultHidden={["previous", "pct", "previous_daily_avg", "current_records", "contribution_pct", "status", "current_daily_avg"]} onRowClick={openResource} loading={npResources.isFetching} maxHeight={440} />
            </Section>
          </Grid>
          <Grid size={{ xs: 12, xl: 6 }}>
            <Section title="Largest Non-Production changes" subtitle="Ranked by absolute change" noPadding testId="nonprod-movers">
              <DataTable data={npMovers.data?.data ?? []} columns={resCols} storageKey="env-np-movers" defaultHidden={["previous_daily_avg", "current_records", "current_daily_avg", "share_of_total", "status", "contribution_pct"]} onRowClick={openResource} loading={npMovers.isFetching} maxHeight={440} />
            </Section>
          </Grid>
          <Grid size={{ xs: 12, xl: 6 }}>
            <Section title="Open Non-Production anomalies" subtitle={anomalies.data ? `${anomalies.data.meta.total} open` : " "} noPadding testId="nonprod-anomalies">
              <DataTable data={anomalies.data?.data ?? []} columns={anomalyCols} storageKey="env-np-anomalies" emptyMessage="No open Non-Production anomalies." loading={anomalies.isFetching} />
            </Section>
          </Grid>
          <Grid size={{ xs: 12, xl: 6 }}>
            <Section
              title="Non-Production savings opportunities"
              subtitle={savings.data ? `Estimated ${money(savings.data.meta.open_estimated_monthly_savings, currency)} / month (estimate, not realised)` : " "}
              noPadding
              testId="nonprod-savings"
              actions={<MuiLink component={Link} href={link("/savings", { env: "non_production" })} underline="hover" sx={{ fontSize: 12.5, fontWeight: 600 }}>All savings</MuiLink>}
            >
              <DataTable data={savings.data?.data ?? []} columns={savingsCols} storageKey="env-np-savings" emptyMessage="No Non-Production savings opportunities." loading={savings.isFetching} />
            </Section>
          </Grid>
        </Grid>
      </Stack>
    </Box>
  );
}
