"use client";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { Alert, Box, Button, Chip, FormControl, Grid, InputLabel, MenuItem, Paper, Select, Stack, Table, TableBody, TableCell, TableRow, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import { useMemo, useState } from "react";
import EChart from "@/charts/EChart";
import { DeltaText, MoneyText } from "@/components/common/Delta";
import { PageHeader } from "@/components/common/PageHeader";
import { Section } from "@/components/common/Section";
import { SeverityChip, StatusChip } from "@/components/common/StatusChip";
import { ChartSkeleton, EmptyState, ErrorState, Warnings } from "@/components/common/States";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { bucketLabel, dateTime, longDate, money, num, pct, periodText, shortDate, titleCase } from "@/lib/format";
import type { GroupItem, ReportMeta, Totals } from "@/lib/types";
import { useApi } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { comparisonColumns } from "@/tables/columns";
import { surface } from "@/styles/tokens";
import { costSeriesOption, DecompositionPanels, quantityOption, RecordsTable, Stat, StatStrip, type Decomposition } from "../comparison/shared";
import type { AnomalySummary } from "../anomalies/AnomaliesPage";

interface ResourceInfo {
  id: number;
  resource_id: string;
  resource_key: string;
  resource_name: string | null;
  resource_type: string | null;
  resource_group: string | null;
  region: string | null;
  sku: string | null;
  service_category: string | null;
  subscription_id: string;
  subscription_name: string;
  application_key: string;
  application: string;
  environment_code: string;
  environment: string;
  allocation_status: string | null;
  owner: string | null;
  cost_center: string | null;
  tags: Record<string, string>;
  first_seen_date: string | null;
  last_seen_date: string | null;
  is_demo: boolean;
}
interface DetailData {
  resource: ResourceInfo;
  totals: Totals;
  meters: GroupItem[];
  anomaly_count: number;
  open_anomaly_count: number;
  savings: { id: number; title: string; estimated_monthly_savings: number | null; status: string; evidence_source: string }[];
}
interface History {
  daily: { date: string; cost: number }[];
  monthly: { month: string; cost: number }[];
  meters: { meter_name: string | null; unit: string | null; cost: number[]; quantity: number[]; total: number }[];
  dates: string[];
}
interface Activity {
  available: boolean;
  reason: string | null;
  events: { timestamp: string; operation: string | null; status: string | null; caller: string | null; level: string | null }[];
  note?: string;
}

function Attr({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <TableRow>
      <TableCell sx={{ color: "text.secondary", width: 150, border: 0, py: 0.5, pl: 0, verticalAlign: "top" }}>{label}</TableCell>
      <TableCell sx={{ border: 0, py: 0.5, wordBreak: "break-word" }}>{children ?? "—"}</TableCell>
    </TableRow>
  );
}

export default function ResourceDetailPage({ id }: { id: string }) {
  const link = useLinkWithFilters();
  const { apiParams } = useGlobalFilters();
  const detail = useApi<{ data: DetailData; meta: ReportMeta }>(`/resources/${id}`, apiParams);
  const history = useApi<{ data: History; meta: ReportMeta }>(`/resources/${id}/history`, apiParams);
  const meters = useApi<{ data: Decomposition; meta: ReportMeta }>(detail.data?.meta.comparison_period ? `/resources/${id}/meters` : null, apiParams);
  const anomalies = useApi<{ data: AnomalySummary[] }>(`/resources/${id}/anomalies`);
  const activity = useApi<Activity>(`/resources/${id}/activity`, apiParams, { staleTime: 300_000 });
  const [meterIdx, setMeterIdx] = useState(0);

  const d = detail.data?.data;
  const meta = detail.data?.meta;
  const currency = meta?.currency ?? "USD";
  const hasCmp = !!meta?.comparison_period;
  const h = history.data?.data;
  const r = d?.resource;

  const dailyOpt = useMemo(() => (h ? costSeriesOption(h.daily.map((p) => ({ label: bucketLabel(p.date, "daily"), value: p.cost })), currency, { kind: "bar", name: "Daily cost" }) : null), [h, currency]);
  const monthlyOpt = useMemo(() => (h ? costSeriesOption(h.monthly.map((p) => ({ label: bucketLabel(p.month, "monthly"), value: p.cost })), currency, { kind: "bar", name: "Monthly cost" }) : null), [h, currency]);
  const meter = h?.meters[Math.min(meterIdx, Math.max((h?.meters.length ?? 1) - 1, 0))];
  const qtyOpt = useMemo(() => (h && meter ? quantityOption(h.dates, meter.quantity, meter.unit ?? "units", meter.meter_name ?? "Quantity") : null), [h, meter]);
  const meterCols = useMemo(() => comparisonColumns({ currency, hasComparison: hasCmp, labelHeader: "Meter" }), [currency, hasCmp]);
  const anomalyCols = useMemo<ColumnDef<AnomalySummary, unknown>[]>(
    () => [
      { accessorKey: "anomaly_ref", header: "ID", size: 110, cell: ({ row }) => <Link href={link(`/anomalies/${row.original.id}`)} style={{ color: "#0f6cbd", fontWeight: 600, textDecoration: "none" }}>{row.original.anomaly_ref}</Link> },
      { accessorKey: "severity", header: "Severity", size: 120, cell: ({ getValue }) => <SeverityChip severity={getValue() as string} /> },
      { accessorKey: "title", header: "Anomaly", size: 240 },
      { accessorKey: "detection_date", header: "Detected", size: 110, cell: ({ getValue }) => shortDate(getValue() as string) },
      { accessorKey: "absolute_increase", header: "Increase", size: 120, meta: { numeric: true }, cell: ({ row }) => <DeltaText value={row.original.absolute_increase} currency={row.original.currency} /> },
      { accessorKey: "status", header: "Status", size: 120, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
    ],
    [link],
  );

  if (detail.error) return <Paper variant="outlined"><ErrorState error={detail.error} onRetry={() => detail.refetch()} /></Paper>;
  if (!d || !r) return <Paper variant="outlined" sx={{ p: 2 }}><ChartSkeleton height={300} /></Paper>;

  const explorerHref = link("/explorer", { drill: JSON.stringify([{ dim: "resource", key: r.resource_key, label: r.resource_name ?? r.resource_key }]), group: "meter", chart: "stacked" });
  const investigateHref = link("/investigation", { resource: r.resource_id });

  return (
    <Box data-testid="resource-detail">
      <Button component={Link} href={link("/resources")} size="small" startIcon={<ArrowBackIcon fontSize="small" />} sx={{ mb: 1 }}>
        All resources
      </Button>
      <PageHeader
        title={r.resource_name ?? r.resource_key}
        actions={
          <>
            <Button component={Link} href={explorerHref} variant="outlined" color="inherit" data-testid="resource-explorer-link">Open in Cost Explorer</Button>
            <Button component={Link} href={investigateHref} variant="contained" data-testid="resource-investigate-link">Investigate what changed</Button>
          </>
        }
      >
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
          {[r.service_category, r.resource_type, r.region, r.sku].filter(Boolean).map((x) => <Chip key={x as string} label={x} variant="outlined" />)}
          {r.is_demo && <StatusChip value="demo" label="Demo data" />}
        </Stack>
      </PageHeader>
      <Stack spacing={2}>
        <Warnings warnings={meta?.warnings} />
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 5 }}>
            <Paper variant="outlined" sx={{ p: 2, height: "100%" }} data-testid="resource-info">
              <Typography variant="h3" sx={{ mb: 1 }}>Resource information</Typography>
              <Table size="small">
                <TableBody>
                  <Attr label="Resource ID"><Typography variant="caption" sx={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", color: "text.primary" }}>{r.resource_id}</Typography></Attr>
                  <Attr label="Subscription">{r.subscription_name}<Typography variant="caption" component="div">{r.subscription_id}</Typography></Attr>
                  <Attr label="Application">{r.application}</Attr>
                  <Attr label="Environment">{r.environment}</Attr>
                  <Attr label="Allocation"><StatusChip value={r.allocation_status ?? "unallocated"} /></Attr>
                  <Attr label="Resource group">{r.resource_group}</Attr>
                  <Attr label="Owner">{r.owner ?? <Typography variant="caption">Untagged</Typography>}</Attr>
                  <Attr label="Cost center">{r.cost_center}</Attr>
                  <Attr label="First / last billed">{longDate(r.first_seen_date)} → {longDate(r.last_seen_date)}</Attr>
                </TableBody>
              </Table>
              <Typography variant="subtitle2" sx={{ mt: 1.5, mb: 0.75 }}>Tags</Typography>
              <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap data-testid="resource-tags">
                {Object.keys(r.tags).length ? Object.entries(r.tags).map(([k, v]) => <Chip key={k} label={`${k}: ${v}`} variant="outlined" sx={{ fontWeight: 500 }} />) : <Typography variant="caption">No tags</Typography>}
              </Stack>
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, lg: 7 }}>
            <Stack spacing={2} sx={{ height: "100%" }}>
              <StatStrip testId="resource-totals">
                <Stat label={`Current · ${periodText(meta?.period)}`} value={money(d.totals.current, currency)} testId="resource-current" />
                <Stat label={hasCmp ? `Previous · ${periodText(meta?.comparison_period)}` : "Comparison"} value={hasCmp ? money(d.totals.previous, currency) : "None"} />
                <Stat label="Difference" value={hasCmp ? <DeltaText value={d.totals.diff} currency={currency} /> : "—"} sub={hasCmp && d.totals.pct !== null ? pct(d.totals.pct) : undefined} />
                <Stat label="Daily average" value={money(d.totals.current_daily_avg, currency)} />
              </StatStrip>
              <StatStrip>
                <Stat label="Anomalies" value={d.anomaly_count} sub={`${d.open_anomaly_count} open`} />
                <Stat label="Savings opportunities" value={d.savings.length} sub={d.savings.length ? `est. ${money(d.savings.reduce((s, x) => s + (x.estimated_monthly_savings ?? 0), 0), currency)}/month` : "none identified"} />
                <Stat label="Billing meters" value={d.meters.length} sub="in the current period" />
              </StatStrip>
              {d.savings.length > 0 && (
                <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="resource-savings">
                  <Typography variant="subtitle1" sx={{ mb: 0.75 }}>Potential savings recommendations</Typography>
                  {d.savings.map((sv) => (
                    <Stack key={sv.id} direction="row" spacing={1} alignItems="center" sx={{ py: 0.5 }}>
                      <StatusChip value={sv.evidence_source === "azure_advisor" ? "info" : "neutral"} label={sv.evidence_source === "azure_advisor" ? "Azure Advisor" : "Billing analysis"} tone={sv.evidence_source === "azure_advisor" ? "info" : "neutral"} />
                      <Typography variant="body2" sx={{ flex: 1 }}>{sv.title}</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{sv.estimated_monthly_savings !== null ? `${money(sv.estimated_monthly_savings, currency)}/mo (estimate)` : "Not estimated"}</Typography>
                      <StatusChip value={sv.status} />
                    </Stack>
                  ))}
                </Paper>
              )}
            </Stack>
          </Grid>
        </Grid>

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 7 }}>
            <Section title="Daily expenditure (90 days)" subtitle={`${currency} · ${meta?.cost_type === "amortized" ? "amortized" : "actual"} cost`} testId="resource-daily" table={h ? <DataTable data={h.daily} columns={[{ accessorKey: "date", header: "Date", size: 140 }, { accessorKey: "cost", header: "Cost", size: 140, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> }] as ColumnDef<{ date: string; cost: number }, unknown>[]} maxHeight={300} storageKey="res-daily" /> : undefined}>
              {history.error ? <ErrorState error={history.error} /> : dailyOpt ? <EChart option={dailyOpt} height={260} ariaLabel="Resource daily cost" testId="echart-resource-daily" /> : <ChartSkeleton height={260} />}
            </Section>
          </Grid>
          <Grid size={{ xs: 12, lg: 5 }}>
            <Section title="Monthly expenditure (13 months)" testId="resource-monthly" table={h ? <DataTable data={h.monthly} columns={[{ accessorKey: "month", header: "Month", size: 140, cell: ({ getValue }) => bucketLabel(getValue() as string, "monthly") }, { accessorKey: "cost", header: "Cost", size: 140, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> }] as ColumnDef<{ month: string; cost: number }, unknown>[]} maxHeight={300} storageKey="res-monthly" /> : undefined}>
              {monthlyOpt ? <EChart option={monthlyOpt} height={260} ariaLabel="Resource monthly cost" testId="echart-resource-monthly" /> : <ChartSkeleton height={260} />}
            </Section>
          </Grid>
        </Grid>

        <Section
          title="Usage quantity trend"
          subtitle="Billed quantity per day for one meter at a time (units differ between meters, so they are never plotted on a shared axis). Billed quantity is not CPU or memory utilisation."
          testId="resource-quantity"
          actions={
            h && h.meters.length > 0 ? (
              <FormControl sx={{ minWidth: 240 }}>
                <InputLabel id="qm">Meter</InputLabel>
                <Select labelId="qm" label="Meter" value={String(Math.min(meterIdx, h.meters.length - 1))} onChange={(e) => setMeterIdx(Number(e.target.value))} data-testid="quantity-meter">
                  {h.meters.map((m, i) => (
                    <MenuItem key={i} value={String(i)}>{m.meter_name} ({m.unit})</MenuItem>
                  ))}
                </Select>
              </FormControl>
            ) : undefined
          }
          table={h && meter ? <DataTable data={h.dates.map((dt, i) => ({ date: dt, quantity: meter.quantity[i], cost: meter.cost[i] }))} columns={[{ accessorKey: "date", header: "Date", size: 130 }, { accessorKey: "quantity", header: `Quantity (${meter.unit})`, size: 160, meta: { numeric: true }, cell: ({ getValue }) => num(getValue() as number, 4) }, { accessorKey: "cost", header: "Cost", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> }] as ColumnDef<{ date: string; quantity: number; cost: number }, unknown>[]} maxHeight={300} storageKey="res-qty" /> : undefined}
        >
          {!h ? <ChartSkeleton height={240} /> : !meter ? <EmptyState message="No metered usage in the last 90 days." /> : <EChart option={qtyOpt!} height={240} ariaLabel="Usage quantity trend" testId="echart-resource-quantity" />}
        </Section>

        <Paper variant="outlined" data-testid="resource-meter-costs">
          <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
            <Typography variant="h3">Meter-level cost</Typography>
            <Typography variant="caption">{periodText(meta?.period)}{hasCmp ? ` vs ${periodText(meta?.comparison_period)}` : ""}</Typography>
          </Box>
          <DataTable data={d.meters} columns={meterCols} storageKey="res-meter-costs" defaultHidden={["previous_daily_avg", "current_records", "contribution_pct"]} getRowId={(m) => m.key || "__none__"} />
        </Paper>

        <Box>
          <Typography variant="h2" sx={{ mb: 1 }}>What changed on this resource?</Typography>
          {hasCmp ? (
            <DecompositionPanels data={meters.data?.data} meta={meters.data?.meta} loading={meters.isFetching} error={meters.error} onRetry={() => meters.refetch()} showResources={false} testPrefix="resource-decomp" />
          ) : (
            <Alert severity="info">Select a period with a comparison to see the meter-level decomposition.</Alert>
          )}
        </Box>

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 7 }}>
            <Paper variant="outlined" sx={{ height: "100%" }} data-testid="resource-anomalies">
              <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
                <Typography variant="h3">Anomaly history</Typography>
              </Box>
              <DataTable data={anomalies.data?.data ?? []} columns={anomalyCols} loading={anomalies.isLoading} storageKey="res-anomalies" emptyMessage="No anomalies detected for this resource." getRowId={(a) => String(a.id)} />
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, lg: 5 }}>
            <Paper variant="outlined" sx={{ height: "100%" }} data-testid="resource-activity">
              <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
                <Typography variant="h3">Configuration changes (Activity Log)</Typography>
                <Typography variant="caption">Optional supporting evidence — correlate with billing changes before concluding.</Typography>
              </Box>
              {!activity.data ? (
                <Box sx={{ p: 2 }}><ChartSkeleton height={80} /></Box>
              ) : !activity.data.available ? (
                <Alert severity="info" sx={{ m: 1.5 }}>{activity.data.reason}</Alert>
              ) : activity.data.events.length === 0 ? (
                <EmptyState title="No Activity Log events" message="No management operations were recorded for this resource in the period." />
              ) : (
                <Table size="small">
                  <TableBody>
                    {activity.data.events.map((e, i) => (
                      <TableRow key={i}>
                        <TableCell sx={{ whiteSpace: "nowrap" }}>{dateTime(e.timestamp)}</TableCell>
                        <TableCell>{e.operation}</TableCell>
                        <TableCell>{e.status}</TableCell>
                        <TableCell>{e.caller}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </Paper>
          </Grid>
        </Grid>

        <Paper variant="outlined" data-testid="resource-records">
          <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
            <Typography variant="h3">Billing records</Typography>
            <Typography variant="caption">Current and comparison period rows for this resource, as ingested from the cost exports ({titleCase(meta?.cost_type)} cost).</Typography>
          </Box>
          <RecordsTable path={`/resources/${id}/records`} params={apiParams} testId="resource-records-table" />
        </Paper>
      </Stack>
    </Box>
  );
}
