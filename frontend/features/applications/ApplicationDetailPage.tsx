"use client";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { Box, Button, Grid, Link as MuiLink, Paper, Stack, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo } from "react";
import EChart from "@/charts/EChart";
import { barOption, donutOption } from "@/charts/options";
import { DeltaText } from "@/components/common/Delta";
import { PageHeader } from "@/components/common/PageHeader";
import { Section } from "@/components/common/Section";
import { SeverityChip, StatusChip } from "@/components/common/StatusChip";
import { ChartSkeleton, EmptyState, ErrorState, Warnings } from "@/components/common/States";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { resourceIdFor } from "@/lib/drill";
import { compactMoney, longDate, money, pct, periodText } from "@/lib/format";
import type { GroupItem, ReportMeta, Totals } from "@/lib/types";
import { useApi } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { comparisonColumns } from "@/tables/columns";
import { surface } from "@/styles/tokens";
import { UtilizationMeter } from "@/features/admin/ui";

interface Detail {
  application: { id: number; code: string; name: string; description: string | null; owner: string | null };
  subscriptions: { subscription_id: string; subscription_name: string; environment: string; enabled: boolean }[];
  totals: Totals;
  by_environment: GroupItem[];
  by_subscription: GroupItem[];
  by_service: GroupItem[];
  by_resource_group: GroupItem[];
  top_resources: GroupItem[];
  top_movers: GroupItem[];
  budget: {
    name: string;
    amount: number;
    actual: number;
    remaining: number;
    utilization_pct: number | null;
    forecast: number;
    forecast_utilization_pct: number | null;
    forecast_variance: number | null;
    forecast_method_label: string;
    period_start: string;
    period_end: string;
    currency: string;
    forecast_exceeds_budget: boolean;
  } | null;
  anomalies: { id: number; title: string; severity: string; status: string; detection_date: string; absolute_increase: number }[];
  savings: { id: number; title: string; estimated_monthly_savings: number | null; status: string }[];
}

function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <Box sx={{ px: 2, py: 1.25, minWidth: 150 }}>
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

function GroupCard({ title, groups, currency, hasCmp, labelHeader, chart, dimension, onPick, testId }: { title: string; groups: GroupItem[]; currency: string; hasCmp: boolean; labelHeader: string; chart: "bar" | "donut"; dimension: string; onPick?: (g: GroupItem) => void; testId: string }) {
  const option = useMemo(
    () => (chart === "donut" ? donutOption(groups, { currency, dimension }) : barOption(groups, { currency, grouped: hasCmp, hasComparison: hasCmp, max: 12 })),
    [chart, groups, currency, dimension, hasCmp],
  );
  const cols = useMemo(() => comparisonColumns({ currency, hasComparison: hasCmp, labelHeader, onLabelClick: onPick }), [currency, hasCmp, labelHeader, onPick]);
  return (
    <Section title={title} testId={testId} table={<DataTable data={groups} columns={cols} storageKey={`app-detail-${dimension}`} defaultHidden={["previous_daily_avg", "current_records", "current_daily_avg", "contribution_pct"]} onRowClick={onPick} maxHeight={320} />}>
      {groups.length === 0 ? <EmptyState message="No cost in this period." /> : <EChart option={option} height={260} ariaLabel={`${title} chart`} onClick={onPick ? (p) => { const g = groups.find((x) => x.label === p.name); if (g) onPick(g); } : undefined} />}
    </Section>
  );
}

export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const link = useLinkWithFilters();
  const { apiParams } = useGlobalFilters();
  const params = useMemo(() => ({ ...apiParams, application: undefined }), [apiParams]);
  const q = useApi<{ data: Detail; meta: ReportMeta }>(`/applications/${id}`, params);
  const d = q.data?.data;
  const meta = q.data?.meta;
  const currency = meta?.currency ?? "USD";
  const hasCmp = !!meta?.comparison_period;

  const openResource = async (g: GroupItem) => {
    if (!g.key) return;
    const rid = await resourceIdFor(g.key, params);
    if (rid) router.push(link(`/resources/${rid}`));
  };
  const explore = (extra: Record<string, string>) => router.push(link("/explorer", { ...extra }));
  const appDrill = (dim: string, g: GroupItem) => JSON.stringify([{ dim: "application", key: String(id), label: d?.application.name ?? "Application" }, { dim, key: g.key, label: g.label }]);

  const resCols = useMemo(() => comparisonColumns({ currency, hasComparison: hasCmp, labelHeader: "Resource", onLabelClick: openResource }), [currency, hasCmp]); // eslint-disable-line react-hooks/exhaustive-deps
  const anomalyCols = useMemo<ColumnDef<Detail["anomalies"][number], unknown>[]>(
    () => [
      { accessorKey: "severity", header: "Severity", size: 110, cell: ({ getValue }) => <SeverityChip severity={getValue() as string} /> },
      { accessorKey: "title", header: "Anomaly", size: 300, cell: ({ row }) => <MuiLink component={Link} href={link(`/anomalies/${row.original.id}`)} underline="hover" sx={{ fontWeight: 600 }}>{row.original.title}</MuiLink> },
      { accessorKey: "detection_date", header: "Detected", size: 120, cell: ({ getValue }) => longDate(getValue() as string) },
      { accessorKey: "absolute_increase", header: "Increase", size: 120, meta: { numeric: true }, cell: ({ getValue }) => <DeltaText value={getValue() as number} currency={currency} /> },
      { accessorKey: "status", header: "Status", size: 120, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
    ],
    [currency, link],
  );

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  return (
    <Box data-testid="application-detail-page">
      <PageHeader
        title={d?.application.name ?? "Application"}
        subtitle={meta ? `${d?.application.description ?? ""}${d?.application.description ? " · " : ""}${periodText(meta.period)}${hasCmp ? ` vs ${periodText(meta.comparison_period)}` : ""} · ${currency}` : " "}
        actions={
          <>
            <Button variant="text" startIcon={<ArrowBackIcon fontSize="small" />} component={Link} href={link("/applications")}>
              All applications
            </Button>
            <Button variant="outlined" color="inherit" endIcon={<OpenInNewIcon fontSize="small" />} onClick={() => explore({ drill: JSON.stringify([{ dim: "application", key: String(id), label: d?.application.name ?? "Application" }]), group: "environment", chart: "grouped" })} data-testid="explore-application">
              Explore in Cost Explorer
            </Button>
          </>
        }
      />
      <Stack spacing={2}>
        <Warnings warnings={meta?.warnings} />
        <Paper variant="outlined" sx={{ display: "flex", flexWrap: "wrap" }} data-testid="application-totals">
          <Stat label="Current period" value={d ? money(d.totals.current, currency) : "…"} sub={meta ? periodText(meta.period) : undefined} />
          {hasCmp && <Stat label="Previous period" value={d ? money(d.totals.previous, currency) : "…"} sub={periodText(meta?.comparison_period)} />}
          {hasCmp && <Stat label="Change" value={d ? <DeltaText value={d.totals.diff} currency={currency} /> : "…"} sub={d ? pct(d.totals.pct) : undefined} />}
          <Stat label="Daily average" value={d ? money(d.totals.current_daily_avg, currency) : "…"} />
          <Box sx={{ flex: 1 }} />
          <Box sx={{ px: 2, py: 1.25 }}>
            <Typography variant="caption" component="div">
              Subscriptions
            </Typography>
            {d?.subscriptions.map((s) => (
              <Typography key={s.subscription_id} variant="body2" sx={{ fontWeight: 600 }} noWrap>
                {s.subscription_name} <Typography component="span" variant="caption">· {s.environment}</Typography>
              </Typography>
            ))}
          </Box>
        </Paper>

        {!d ? (
          <ChartSkeleton height={260} />
        ) : (
          <>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, lg: 5 }}>
                <GroupCard title="By environment" groups={d.by_environment} currency={currency} hasCmp={hasCmp} labelHeader="Environment" chart="donut" dimension="environment" testId="app-by-environment" onPick={(g) => explore({ drill: appDrill("environment", g), group: "service_category" })} />
              </Grid>
              <Grid size={{ xs: 12, lg: 7 }}>
                <GroupCard title="By subscription" groups={d.by_subscription} currency={currency} hasCmp={hasCmp} labelHeader="Subscription" chart="bar" dimension="subscription" testId="app-by-subscription" onPick={(g) => explore({ drill: appDrill("subscription", g), group: "service_category" })} />
              </Grid>
              <Grid size={{ xs: 12, lg: 7 }}>
                <GroupCard title="By Azure service" groups={d.by_service} currency={currency} hasCmp={hasCmp} labelHeader="Azure service" chart="bar" dimension="service_category" testId="app-by-service" onPick={(g) => explore({ drill: appDrill("service_category", g), group: "resource" })} />
              </Grid>
              <Grid size={{ xs: 12, lg: 5 }}>
                <Section title="Budget utilisation" subtitle={d.budget ? `${d.budget.name} · ${longDate(d.budget.period_start)} – ${longDate(d.budget.period_end)}` : "No application budget configured"} testId="app-budget">
                  {d.budget ? (
                    <Stack spacing={1.5} sx={{ p: 0.5 }}>
                      <Stack direction="row" justifyContent="space-between">
                        <Typography variant="body2">
                          Actual <b>{money(d.budget.actual, currency)}</b> of {money(d.budget.amount, currency)}
                        </Typography>
                        <Typography variant="body2">{pct(d.budget.utilization_pct, { sign: false })}</Typography>
                      </Stack>
                      <UtilizationMeter utilization={d.budget.utilization_pct} forecastPct={d.budget.forecast_utilization_pct} label="Application budget utilisation" />
                      <Typography variant="body2">
                        Forecast month-end <b>{money(d.budget.forecast, currency)}</b> ({pct(d.budget.forecast_utilization_pct, { sign: false })} of budget) ·{" "}
                        <Box component="span" sx={{ color: d.budget.forecast_exceeds_budget ? "#b42318" : "text.secondary", fontWeight: 600 }}>
                          {d.budget.forecast_exceeds_budget ? `projected overspend ${money(d.budget.forecast_variance, currency)}` : `projected headroom ${money(Math.abs(d.budget.forecast_variance ?? 0), currency)}`}
                        </Box>
                      </Typography>
                      <Typography variant="caption">Forecast method: {d.budget.forecast_method_label}. Forecasts are projections, not actual charges.</Typography>
                    </Stack>
                  ) : (
                    <EmptyState title="No budget" message="Create an application budget on the Budget & Forecast page." action={<Button component={Link} href={link("/budgets")} size="small">Go to budgets</Button>} />
                  )}
                </Section>
              </Grid>
            </Grid>
            <Section title="Resource groups" subtitle="Top 25 by current cost" noPadding testId="app-resource-groups">
              <DataTable data={d.by_resource_group} columns={comparisonColumns({ currency, hasComparison: hasCmp, labelHeader: "Resource group" })} storageKey="app-detail-rg" defaultHidden={["previous_daily_avg", "current_records"]} maxHeight={360} onRowClick={(g) => explore({ drill: appDrill("resource_group", g), group: "resource" })} />
            </Section>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, xl: 6 }}>
                <Section title="Top cost contributors" subtitle="Largest resources by current cost" noPadding testId="app-top-resources">
                  <DataTable data={d.top_resources} columns={resCols} storageKey="app-detail-top" defaultHidden={["previous", "pct", "previous_daily_avg", "current_records", "current_daily_avg", "contribution_pct", "status"]} onRowClick={openResource} maxHeight={420} />
                </Section>
              </Grid>
              <Grid size={{ xs: 12, xl: 6 }}>
                <Section title="Largest cost increases / decreases" subtitle="Ranked by absolute change" noPadding testId="app-top-movers">
                  <DataTable data={d.top_movers} columns={resCols} storageKey="app-detail-movers" defaultHidden={["previous_daily_avg", "current_records", "current_daily_avg", "share_of_total", "status", "contribution_pct"]} onRowClick={openResource} maxHeight={420} />
                </Section>
              </Grid>
              <Grid size={{ xs: 12, xl: 7 }}>
                <Section title="Cost anomalies" subtitle="Most recent detections for this application" noPadding testId="app-anomalies">
                  <DataTable data={d.anomalies} columns={anomalyCols} storageKey="app-detail-anomalies" emptyMessage="No anomalies detected for this application." />
                </Section>
              </Grid>
              <Grid size={{ xs: 12, xl: 5 }}>
                <Section title="Potential savings" subtitle="Estimated monthly savings — not realised" testId="app-savings">
                  {d.savings.length === 0 ? (
                    <EmptyState message="No savings opportunities identified." />
                  ) : (
                    <Stack divider={<Box sx={{ borderTop: `1px solid ${surface.border}` }} />}>
                      {d.savings.map((s) => (
                        <Stack key={s.id} direction="row" alignItems="center" spacing={1} sx={{ py: 1 }}>
                          <Typography variant="body2" sx={{ flex: 1 }} noWrap title={s.title}>
                            {s.title}
                          </Typography>
                          <StatusChip value={s.status} />
                          <Typography variant="body2" sx={{ fontWeight: 600, minWidth: 90, textAlign: "right" }}>
                            {s.estimated_monthly_savings === null ? "Not estimated" : `${compactMoney(s.estimated_monthly_savings, currency)}/mo`}
                          </Typography>
                        </Stack>
                      ))}
                      <Box sx={{ pt: 1 }}>
                        <MuiLink component={Link} href={link("/savings", { app: String(id) })} underline="hover" sx={{ fontSize: 12.5, fontWeight: 600 }}>
                          View savings opportunities
                        </MuiLink>
                      </Box>
                    </Stack>
                  )}
                </Section>
              </Grid>
            </Grid>
          </>
        )}
      </Stack>
    </Box>
  );
}

