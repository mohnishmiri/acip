"use client";
import { Alert, Box, Grid, Link as MuiLink, MenuItem, Paper, Select, Stack, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import { useMemo } from "react";
import { MoneyText } from "@/components/common/Delta";
import { PageHeader } from "@/components/common/PageHeader";
import { Section } from "@/components/common/Section";
import { StatusChip } from "@/components/common/StatusChip";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { useUrlState } from "@/hooks/useUrlState";
import { api } from "@/lib/api";
import { dateTime, money, titleCase } from "@/lib/format";
import { useApi } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { surface } from "@/styles/tokens";
import { errorMessage, KeyValueList, ToastProvider, useCan, useToast } from "@/features/admin/ui";

interface Opportunity {
  id: number;
  rule_code: string;
  title: string;
  resource_name: string | null;
  resource_key: string | null;
  resource_id: number | null;
  application: string;
  environment: string;
  subscription_name: string;
  service_category: string | null;
  currency: string;
  current_monthly_cost: number;
  estimated_monthly_savings: number | null;
  savings_basis: string | null;
  issue: string;
  evidence: Record<string, unknown>;
  recommendation: string;
  evidence_source: string;
  status: string;
  detected_at: string;
  last_evaluated_at: string;
  is_demo: boolean;
}

const STATUSES = ["open", "investigating", "accepted", "dismissed", "implemented"];
const SOURCE_LABEL: Record<string, string> = { billing_analysis: "Billing analysis", azure_advisor: "Azure Advisor" };

function SavingsInner() {
  const { filters } = useGlobalFilters();
  const link = useLinkWithFilters();
  const toast = useToast();
  const qc = useQueryClient();
  const canManage = useCan("manage_savings");
  const [s, set] = useUrlState({ status: "active", source: "" });
  const statusParam = s.status === "active" ? ["open", "investigating", "accepted"] : s.status === "all" ? undefined : [s.status];
  const params = {
    status: statusParam,
    source: s.source ? [s.source] : undefined,
    application: filters.app && /^\d+$/.test(filters.app) ? [filters.app] : undefined,
    environment: filters.env ? [filters.env] : undefined,
  };
  const q = useApi<{ data: Opportunity[]; meta: { total: number; open_estimated_monthly_savings: number; note: string } }>("/savings", params);
  const all = useApi<{ data: Opportunity[] }>("/savings", { application: params.application, environment: params.environment });
  const rows = useMemo(() => q.data?.data ?? [], [q.data]);
  const currency = rows[0]?.currency ?? "USD";

  const summary = useMemo(() => {
    const list = all.data?.data ?? [];
    const active = list.filter((o) => ["open", "investigating", "accepted"].includes(o.status));
    const est = (xs: Opportunity[]) => xs.reduce((t, o) => t + (o.estimated_monthly_savings ?? 0), 0);
    return {
      activeEst: est(active),
      activeCount: active.length,
      notEstimated: active.filter((o) => o.estimated_monthly_savings === null).length,
      billing: est(active.filter((o) => o.evidence_source === "billing_analysis")),
      advisor: est(active.filter((o) => o.evidence_source === "azure_advisor")),
      implemented: list.filter((o) => o.status === "implemented").length,
      dismissed: list.filter((o) => o.status === "dismissed").length,
    };
  }, [all.data]);

  const setStatus = async (o: Opportunity, status: string) => {
    try {
      await api(`/savings/${o.id}/status`, { method: "POST", body: { status } });
      toast(`Status set to ${titleCase(status)}`);
      qc.invalidateQueries({ predicate: (x) => typeof x.queryKey[0] === "string" && ((x.queryKey[0] as string).startsWith("/savings") || (x.queryKey[0] as string).startsWith("/dashboard")) });
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  const columns = useMemo<ColumnDef<Opportunity, unknown>[]>(
    () => [
      {
        accessorKey: "title",
        header: "Opportunity",
        size: 300,
        enableHiding: false,
        cell: ({ row }) => (
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="body2" noWrap sx={{ fontWeight: 600 }} title={row.original.title}>
              {row.original.title}
            </Typography>
            <Typography variant="caption" noWrap component="div" title={row.original.issue}>
              {row.original.issue}
            </Typography>
          </Box>
        ),
      },
      {
        accessorKey: "resource_name",
        header: "Resource",
        size: 175,
        cell: ({ row }) =>
          row.original.resource_id ? (
            <MuiLink component={Link} href={link(`/resources/${row.original.resource_id}`)} underline="hover" onClick={(e) => e.stopPropagation()} sx={{ fontWeight: 600 }}>
              {row.original.resource_name}
            </MuiLink>
          ) : (
            row.original.resource_name ?? <Typography variant="caption">Scope-level</Typography>
          ),
      },
      { accessorKey: "application", header: "Application", size: 110 },
      { accessorKey: "environment", header: "Environment", size: 115 },
      { accessorKey: "subscription_name", header: "Subscription", size: 190 },
      { accessorKey: "service_category", header: "Service", size: 160, cell: ({ getValue }) => (getValue() as string) ?? "—" },
      { accessorKey: "current_monthly_cost", header: "Monthly cost", size: 120, meta: { numeric: true, label: "Current monthly cost" }, cell: ({ row }) => <MoneyText value={row.original.current_monthly_cost} currency={row.original.currency} /> },
      {
        accessorKey: "estimated_monthly_savings",
        header: "Est. savings/mo",
        size: 130,
        meta: { numeric: true, label: "Estimated potential monthly savings" },
        sortUndefined: "last",
        cell: ({ row }) => (row.original.estimated_monthly_savings === null ? <Typography variant="caption">Not estimated</Typography> : <MoneyText value={row.original.estimated_monthly_savings} currency={row.original.currency} bold />),
      },
      { accessorKey: "evidence_source", header: "Evidence", size: 135, meta: { label: "Evidence source" }, cell: ({ getValue }) => <StatusChip value="info" tone={getValue() === "azure_advisor" ? "info" : "neutral"} label={SOURCE_LABEL[getValue() as string] ?? (getValue() as string)} /> },
      {
        accessorKey: "status",
        header: "Status",
        size: 160,
        meta: { label: "Investigation status" },
        cell: ({ row }) =>
          canManage ? (
            <Select
              size="small"
              value={row.original.status}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setStatus(row.original, e.target.value)}
              sx={{ minWidth: 140, "& .MuiSelect-select": { py: "3px" } }}
              inputProps={{ "aria-label": `Status of ${row.original.title}` }}
              data-testid={`savings-status-${row.original.id}`}
            >
              {STATUSES.map((st) => (
                <MenuItem key={st} value={st}>
                  {titleCase(st)}
                </MenuItem>
              ))}
            </Select>
          ) : (
            <StatusChip value={row.original.status} />
          ),
      },
      { accessorKey: "last_evaluated_at", header: "Last evaluated", size: 170, cell: ({ getValue }) => dateTime(getValue() as string) },
    ],
    [canManage, link], // eslint-disable-line react-hooks/exhaustive-deps
  );

  return (
    <Box data-testid="savings-page">
      <PageHeader title="Potential Cost Savings" subtitle="Evidence-based opportunities from billing analysis and (optionally) Azure Advisor. Figures are estimates of potential savings — they are never reported as realised savings." />
      <Stack spacing={2}>
        <Alert severity="info" variant="outlined" sx={{ bgcolor: "#fff" }} data-testid="savings-readonly-note">
          This platform is read-only: it never stops, deletes, resizes or modifies Azure resources. Billing quantities show what was billed, not CPU or memory utilisation — utilisation-based recommendations come from Azure Advisor or Azure Monitor metrics.
        </Alert>
        <Paper variant="outlined" sx={{ display: "flex", flexWrap: "wrap" }} data-testid="savings-summary">
          {[
            { label: "Estimated potential savings / month (open, investigating, accepted)", value: money(summary.activeEst, currency), sub: `${summary.activeCount} opportunities · ${summary.notEstimated} not estimated` },
            { label: "From billing analysis", value: money(summary.billing, currency), sub: "Rule-based evidence from billed usage" },
            { label: "From Azure Advisor", value: money(summary.advisor, currency), sub: "Utilisation-based recommendations" },
            { label: "Marked implemented", value: String(summary.implemented), sub: "Status only — savings are not verified as realised" },
            { label: "Dismissed", value: String(summary.dismissed), sub: "Reviewed and not pursued" },
          ].map((x) => (
            <Box key={x.label} sx={{ px: 2, py: 1.25, flex: 1, minWidth: 200, borderRight: `1px solid ${surface.border}` }}>
              <Typography variant="caption" component="div">
                {x.label}
              </Typography>
              <Typography sx={{ fontSize: 18, fontWeight: 600 }}>{x.value}</Typography>
              <Typography variant="caption" component="div">
                {x.sub}
              </Typography>
            </Box>
          ))}
        </Paper>
        <Section
          title="Opportunities"
          subtitle={q.data ? `${q.data.meta.total} shown · expand a row for evidence, assumptions and recommendation` : " "}
          noPadding
          testId="savings-table-section"
        >
          <DataTable
            data={rows}
            columns={columns}
            loading={q.isFetching}
            error={q.error ? errorMessage(q.error) : null}
            getRowId={(r) => String(r.id)}
            storageKey="savings"
            defaultHidden={["subscription_name", "last_evaluated_at", "service_category"]}
            emptyMessage="No opportunities match the filters."
            testId="savings-table"
            toolbar={
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <ToggleButtonGroup size="small" exclusive value={s.status} onChange={(_, v) => v && set({ status: v })} aria-label="Status filter" data-testid="savings-status-filter">
                  <ToggleButton value="active">Active</ToggleButton>
                  {STATUSES.map((st) => (
                    <ToggleButton key={st} value={st}>
                      {titleCase(st)}
                    </ToggleButton>
                  ))}
                  <ToggleButton value="all">All</ToggleButton>
                </ToggleButtonGroup>
                <Select size="small" displayEmpty value={s.source} onChange={(e) => set({ source: e.target.value })} sx={{ minWidth: 170, "& .MuiSelect-select": { py: "4px" } }} inputProps={{ "aria-label": "Evidence source" }} data-testid="savings-source-filter">
                  <MenuItem value="">All evidence sources</MenuItem>
                  <MenuItem value="billing_analysis">Billing analysis</MenuItem>
                  <MenuItem value="azure_advisor">Azure Advisor</MenuItem>
                </Select>
                <Typography variant="caption">Application / environment follow the global filters.</Typography>
              </Stack>
            }
            renderSubRow={(o) => (
              <Grid container spacing={2} data-testid={`savings-evidence-${o.id}`}>
                <Grid size={{ xs: 12, md: 4 }}>
                  <Typography variant="subtitle2">Identified issue</Typography>
                  <Typography variant="body2" sx={{ mb: 1 }}>
                    {o.issue}
                  </Typography>
                  <Typography variant="subtitle2">Recommendation</Typography>
                  <Typography variant="body2" sx={{ mb: 1 }}>
                    {o.recommendation}
                  </Typography>
                  <Typography variant="subtitle2">Savings basis / assumption</Typography>
                  <Typography variant="body2">{o.savings_basis ?? "—"}</Typography>
                </Grid>
                <Grid size={{ xs: 12, md: 8 }}>
                  <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                    Supporting evidence · source: {SOURCE_LABEL[o.evidence_source] ?? o.evidence_source}
                    {o.is_demo ? " (DEMO)" : ""}
                  </Typography>
                  <KeyValueList data={o.evidence} />
                  <Typography variant="caption" component="div" sx={{ mt: 1 }}>
                    Rule {o.rule_code} · detected {dateTime(o.detected_at)} · last evaluated {dateTime(o.last_evaluated_at)}
                  </Typography>
                </Grid>
              </Grid>
            )}
          />
        </Section>
      </Stack>
    </Box>
  );
}

export default function SavingsPage() {
  return (
    <ToastProvider>
      <SavingsInner />
    </ToastProvider>
  );
}
