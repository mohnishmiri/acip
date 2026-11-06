"use client";
import DownloadForOfflineOutlinedIcon from "@mui/icons-material/DownloadForOfflineOutlined";
import CloseIcon from "@mui/icons-material/Close";
import CloudSyncOutlinedIcon from "@mui/icons-material/CloudSyncOutlined";
import HistoryIcon from "@mui/icons-material/History";
import InsightsOutlinedIcon from "@mui/icons-material/InsightsOutlined";
import ReplayIcon from "@mui/icons-material/Replay";
import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Box, Button, Drawer, Grid, IconButton, LinearProgress, Paper, Stack, Tab, Tabs, Tooltip, Typography } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { PageHeader } from "@/components/common/PageHeader";
import { Section } from "@/components/common/Section";
import { StatusChip } from "@/components/common/StatusChip";
import { ErrorState } from "@/components/common/States";
import { useUrlState } from "@/hooks/useUrlState";
import { api } from "@/lib/api";
import { dateTime, longDate, money, num, titleCase } from "@/lib/format";
import type { Freshness } from "@/lib/types";
import { useApi } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { surface } from "@/styles/tokens";
import { useAuth } from "@/components/layout/AuthProvider";
import { ConfirmDialog, errorMessage, FormDialog, KeyValueList, RhfSelect, RhfText, ToastProvider, useCan, useToast } from "@/features/admin/ui";

interface Job {
  id: number;
  job_type: string;
  status: string;
  subscription_id: string | null;
  subscription_name: string | null;
  dataset_type: string | null;
  params: Record<string, unknown>;
  attempts: number;
  max_attempts: number;
  next_attempt_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  progress: { pct?: number; step?: string } | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  triggered_by: string;
  created_at: string;
}
interface JobDetail extends Job {
  errors: { id: number; error_type: string; message: string; row_number: number | null; created_at: string }[];
  logs: { operation: string; level: string; message: string; details: Record<string, unknown> | null; created_at: string }[];
}
interface Run {
  id: number;
  subscription_name: string;
  dataset_type: string;
  run_key: string;
  period_start: string | null;
  period_end: string | null;
  submitted_at: string | null;
  status: string;
  file_count: number;
  row_count: number | null;
  rows_rejected: number | null;
  total_cost: number | null;
  days_applied: number | null;
  days_skipped_newer: number | null;
  applied_at: string | null;
  error: string | null;
}
interface FileRow {
  id: number;
  subscription_name: string;
  dataset_type: string;
  blob_path: string;
  size_bytes: number | null;
  content_hash: string;
  status: string;
  rows_read: number | null;
  rows_loaded: number | null;
  rows_rejected: number | null;
  cost_total: number | null;
  detected_schema: string | null;
  normalizer_version: string | null;
  processed_at: string | null;
  error: string | null;
}
interface ErrRow {
  id: number;
  job_id: number | null;
  export_run_id: number | null;
  subscription_name: string | null;
  row_number: number | null;
  error_type: string;
  message: string;
  created_at: string;
}
type Paged<T> = { data: T[]; meta: { total: number; page: number; page_size: number } };
type SubFresh = Freshness["subscriptions"][number];

const JOB_LABEL: Record<string, string> = {
  sync_subscription: "Synchronise exports",
  reprocess_subscription: "Reprocess date range",
  backfill_cost_details: "Cost Details backfill",
  reattribute: "Re-apply allocation rules",
  analytics: "Analytics refresh",
  advisor_import: "Azure Advisor import",
  local_export: "Pull to local exports",
  retention: "Retention",
};

const reprocessSchema = z
  .object({
    subscription_id: z.string().min(1, "Select a subscription"),
    period_from: z.string().min(1, "Required"),
    period_to: z.string().min(1, "Required"),
    dataset_types: z.array(z.enum(["actual", "amortized", "focus"])),
  })
  .refine((v) => v.period_to >= v.period_from, { path: ["period_to"], message: "End must be on or after start" });
type ReprocessValues = z.infer<typeof reprocessSchema>;

const backfillSchema = z
  .object({
    subscription_id: z.string().min(1, "Select a subscription"),
    metric: z.enum(["ActualCost", "AmortizedCost"]),
    start_date: z.string().min(1, "Required"),
    end_date: z.string().min(1, "Required"),
  })
  .refine((v) => v.end_date >= v.start_date, { path: ["end_date"], message: "End must be on or after start" })
  .refine((v) => (new Date(v.end_date).getTime() - new Date(v.start_date).getTime()) / 86400000 <= 31, { path: ["end_date"], message: "The Cost Details API accepts at most one month per request" });
type BackfillValues = z.infer<typeof backfillSchema>;

const localSchema = z.object({
  months: z.number({ error: "Enter a number" }).int().min(1, "At least 1 month").max(13, "At most 13 months"),
  dataset_types: z.array(z.enum(["actual", "amortized"])).min(1, "Select at least one cost type"),
  subscription_ids: z.array(z.string()),
});
type LocalValues = z.infer<typeof localSchema>;

function Pager<T>({ path, columns, storageKey, testId, defaultHidden, renderSubRow, emptyMessage }: { path: string; columns: ColumnDef<T, unknown>[]; storageKey: string; testId: string; defaultHidden?: string[]; renderSubRow?: (r: T) => React.ReactNode; emptyMessage?: string }) {
  const [paging, setPaging] = useState({ page: 1, size: 50 });
  const q = useApi<Paged<T>>(path, { page: paging.page, page_size: paging.size });
  return (
    <DataTable
      data={q.data?.data ?? []}
      columns={columns}
      loading={q.isFetching}
      error={q.error ? errorMessage(q.error) : null}
      serverPaging={{ page: paging.page, pageSize: paging.size, total: q.data?.meta.total ?? 0, onChange: (page, size) => setPaging({ page, size }) }}
      storageKey={storageKey}
      testId={testId}
      defaultHidden={defaultHidden}
      renderSubRow={renderSubRow}
      emptyMessage={emptyMessage}
    />
  );
}

function DataInner() {
  const qc = useQueryClient();
  const toast = useToast();
  const canIngest = useCan("ingestion");
  const [s, set] = useUrlState({ tab: "jobs" });
  const status = useApi<{ freshness: Freshness; active_jobs: Job[] }>("/ingestion/status", undefined, { refetchInterval: (q) => ((q.state.data as { active_jobs: Job[] } | undefined)?.active_jobs.length ? 4000 : 30000) });
  const active = status.data?.active_jobs.length ?? 0;
  const [jobsPaging, setJobsPaging] = useState({ page: 1, size: 25 });
  const jobs = useApi<Paged<Job>>("/ingestion/jobs", { page: jobsPaging.page, page_size: jobsPaging.size }, { refetchInterval: active ? 4000 : false });
  const fresh = status.data?.freshness;
  const subs = fresh?.subscriptions ?? [];

  const [confirmSync, setConfirmSync] = useState<{ subscription?: SubFresh } | null>(null);
  const [reprocessOpen, setReprocessOpen] = useState<string | null>(null);
  const [backfillOpen, setBackfillOpen] = useState(false);
  const [localOpen, setLocalOpen] = useState(false);
  const { config } = useAuth();
  const localMode = !!config?.azure_integration && config?.export_source === "local";
  const [jobId, setJobId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const detail = useApi<JobDetail>(jobId ? `/ingestion/jobs/${jobId}` : null, undefined, { refetchInterval: active ? 4000 : false });

  const refreshAll = () => qc.invalidateQueries({ predicate: (q) => typeof q.queryKey[0] === "string" && ((q.queryKey[0] as string).startsWith("/ingestion") || (q.queryKey[0] as string).startsWith("/meta/freshness")) });

  const doSync = async (subscriptionIds?: string[]) => {
    setBusy(true);
    try {
      const r = await api<{ jobs: { subscription_id: string; job_id: number; created: boolean }[] }>("/ingestion/trigger", { method: "POST", body: { subscription_ids: subscriptionIds ?? null } });
      const created = r.jobs.filter((j) => j.created).length;
      toast(`${created} synchronisation job(s) queued${r.jobs.length - created ? `, ${r.jobs.length - created} already queued/running` : ""}`);
      refreshAll();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
      setConfirmSync(null);
    }
  };

  const reprocessForm = useForm<ReprocessValues>({ resolver: zodResolver(reprocessSchema), defaultValues: { subscription_id: "", period_from: "", period_to: "", dataset_types: [] } });
  useEffect(() => {
    if (reprocessOpen !== null) reprocessForm.reset({ subscription_id: reprocessOpen, period_from: "", period_to: "", dataset_types: [] });
  }, [reprocessOpen]); // eslint-disable-line react-hooks/exhaustive-deps
  const backfillForm = useForm<BackfillValues>({ resolver: zodResolver(backfillSchema), defaultValues: { subscription_id: "", metric: "ActualCost", start_date: "", end_date: "" } });
  const [formError, setFormError] = useState<string | null>(null);
  const localForm = useForm<LocalValues>({ resolver: zodResolver(localSchema), defaultValues: { months: 3, dataset_types: ["actual", "amortized"], subscription_ids: [] } });

  const subOptions = subs.map((x) => ({ value: x.subscription_id, label: `${x.subscription_name}${x.is_demo ? " (demo)" : ""}` }));

  const subCols = useMemo<ColumnDef<SubFresh, unknown>[]>(
    () => [
      { accessorKey: "subscription_name", header: "Subscription", size: 240, enableHiding: false, cell: ({ row }) => <Box><Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{row.original.subscription_name}</Typography><Typography variant="caption" noWrap component="div">{row.original.subscription_id}</Typography></Box> },
      { accessorKey: "status", header: "Status", size: 125, cell: ({ getValue }) => <StatusChip value={getValue() as string} label={getValue() === "demo" ? "Demo data" : undefined} /> },
      { id: "latest_actual", header: "Latest (actual)", size: 125, meta: { label: "Latest usage date (actual)" }, accessorFn: (r) => r.latest_usage_date.actual, cell: ({ getValue }) => longDate(getValue() as string | null) },
      { id: "latest_amortized", header: "Latest (amortized)", size: 140, meta: { label: "Latest usage date (amortized)" }, accessorFn: (r) => r.latest_usage_date.amortized, cell: ({ getValue }) => longDate(getValue() as string | null) },
      { id: "earliest", header: "History from", size: 130, accessorFn: (r) => r.earliest_usage_date.actual, cell: ({ getValue }) => longDate(getValue() as string | null) },
      { accessorKey: "data_lag_hours", header: "Data lag", size: 85, meta: { numeric: true }, cell: ({ getValue }) => (getValue() === null ? "—" : `${num(getValue() as number, 0)} h`) },
      { accessorKey: "last_successful_sync_at", header: "Last successful sync", size: 175, cell: ({ getValue }) => dateTime(getValue() as string | null) },
      { accessorKey: "last_sync_attempt_at", header: "Last attempt", size: 180, cell: ({ getValue }) => dateTime(getValue() as string | null) },
      { accessorKey: "last_sync_error", header: "Last error", size: 200, cell: ({ getValue }) => (getValue() ? <Typography variant="caption" color="error" title={getValue() as string} noWrap component="div">{getValue() as string}</Typography> : "—") },
      {
        id: "actions",
        header: "",
        size: 170,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) =>
          canIngest ? (
            <Stack direction="row" spacing={0.5}>
              <Button size="small" onClick={() => setConfirmSync({ subscription: row.original })} data-testid={`sync-${row.original.subscription_id}`}>
                Sync
              </Button>
              <Button size="small" onClick={() => { setFormError(null); setReprocessOpen(row.original.subscription_id); }}>
                Reprocess
              </Button>
            </Stack>
          ) : null,
      },
    ],
    [canIngest],
  );

  const jobCols = useMemo<ColumnDef<Job, unknown>[]>(
    () => [
      { accessorKey: "id", header: "Job", size: 70, meta: { numeric: true } },
      { accessorKey: "job_type", header: "Type", size: 190, cell: ({ getValue }) => JOB_LABEL[getValue() as string] ?? titleCase(getValue() as string) },
      { accessorKey: "subscription_name", header: "Subscription", size: 210, cell: ({ getValue }) => (getValue() as string) ?? "All / n.a." },
      { accessorKey: "status", header: "Status", size: 120, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
      {
        id: "progress",
        header: "Progress",
        size: 220,
        accessorFn: (r) => r.progress?.pct ?? 0,
        cell: ({ row }) => (
          <Box sx={{ minWidth: 0 }}>
            {row.original.status === "running" && <LinearProgress variant="determinate" value={row.original.progress?.pct ?? 0} sx={{ height: 5, mb: 0.25 }} />}
            <Typography variant="caption" noWrap component="div" title={row.original.progress?.step}>
              {row.original.progress?.step ?? "—"}
            </Typography>
          </Box>
        ),
      },
      { id: "attempts", header: "Attempts", size: 90, accessorFn: (r) => r.attempts, cell: ({ row }) => `${row.original.attempts}/${row.original.max_attempts}` },
      { accessorKey: "created_at", header: "Queued", size: 170, cell: ({ getValue }) => dateTime(getValue() as string) },
      { accessorKey: "finished_at", header: "Finished", size: 170, cell: ({ getValue }) => dateTime(getValue() as string | null) },
      { accessorKey: "triggered_by", header: "Triggered by", size: 160 },
      { accessorKey: "error_message", header: "Error", size: 260, cell: ({ getValue }) => (getValue() ? <Typography variant="caption" color="error" noWrap component="div" title={getValue() as string}>{getValue() as string}</Typography> : "—") },
      {
        id: "actions",
        header: "",
        size: 90,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) =>
          canIngest && ["failed", "cancelled", "partial"].includes(row.original.status) ? (
            <Button
              size="small"
              startIcon={<ReplayIcon fontSize="small" />}
              data-testid={`retry-${row.original.id}`}
              onClick={async (e) => {
                e.stopPropagation();
                try {
                  await api(`/ingestion/retry/${row.original.id}`, { method: "POST" });
                  toast(`Job ${row.original.id} re-queued`);
                  refreshAll();
                } catch (err) {
                  toast(errorMessage(err), "error");
                }
              }}
            >
              Retry
            </Button>
          ) : null,
      },
    ],
    [canIngest], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const runCols = useMemo<ColumnDef<Run, unknown>[]>(
    () => [
      { accessorKey: "id", header: "Run", size: 70, meta: { numeric: true } },
      { accessorKey: "subscription_name", header: "Subscription", size: 200 },
      { accessorKey: "dataset_type", header: "Dataset", size: 100, cell: ({ getValue }) => titleCase(getValue() as string) },
      { id: "period", header: "Period", size: 190, accessorFn: (r) => r.period_start, cell: ({ row }) => `${longDate(row.original.period_start)} – ${longDate(row.original.period_end)}` },
      { accessorKey: "submitted_at", header: "Export submitted", size: 170, cell: ({ getValue }) => dateTime(getValue() as string | null) },
      { accessorKey: "status", header: "Status", size: 140, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
      { accessorKey: "row_count", header: "Rows", size: 90, meta: { numeric: true }, cell: ({ getValue }) => num(getValue() as number | null, 0) },
      { accessorKey: "rows_rejected", header: "Rejected", size: 90, meta: { numeric: true }, cell: ({ getValue }) => num(getValue() as number | null, 0) },
      { accessorKey: "total_cost", header: "Control total", size: 130, meta: { numeric: true }, cell: ({ getValue }) => money(getValue() as number | null) },
      { accessorKey: "days_applied", header: "Days applied", size: 110, meta: { numeric: true } },
      { accessorKey: "days_skipped_newer", header: "Days kept (newer data)", size: 160, meta: { numeric: true } },
      { accessorKey: "run_key", header: "Run key", size: 300, cell: ({ getValue }) => <Typography variant="caption" noWrap title={getValue() as string} component="div">{getValue() as string}</Typography> },
      { accessorKey: "error", header: "Error", size: 260, cell: ({ getValue }) => (getValue() ? <Typography variant="caption" color="error" noWrap component="div" title={getValue() as string}>{getValue() as string}</Typography> : "—") },
    ],
    [],
  );

  const fileCols = useMemo<ColumnDef<FileRow, unknown>[]>(
    () => [
      { accessorKey: "id", header: "File", size: 70, meta: { numeric: true } },
      { accessorKey: "subscription_name", header: "Subscription", size: 200 },
      { accessorKey: "dataset_type", header: "Dataset", size: 100, cell: ({ getValue }) => titleCase(getValue() as string) },
      { accessorKey: "blob_path", header: "Source path", size: 360, cell: ({ getValue }) => <Typography variant="caption" noWrap title={getValue() as string} component="div">{getValue() as string}</Typography> },
      { accessorKey: "status", header: "Status", size: 110, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
      { accessorKey: "rows_read", header: "Rows read", size: 100, meta: { numeric: true }, cell: ({ getValue }) => num(getValue() as number | null, 0) },
      { accessorKey: "rows_loaded", header: "Loaded", size: 90, meta: { numeric: true }, cell: ({ getValue }) => num(getValue() as number | null, 0) },
      { accessorKey: "rows_rejected", header: "Rejected", size: 90, meta: { numeric: true }, cell: ({ getValue }) => num(getValue() as number | null, 0) },
      { accessorKey: "cost_total", header: "Cost total", size: 120, meta: { numeric: true }, cell: ({ getValue }) => money(getValue() as number | null) },
      { accessorKey: "detected_schema", header: "Schema", size: 170 },
      { accessorKey: "normalizer_version", header: "Normaliser", size: 110 },
      { accessorKey: "content_hash", header: "SHA-256", size: 160, cell: ({ getValue }) => <Typography variant="caption" sx={{ fontFamily: "monospace" }} title={getValue() as string}>{(getValue() as string).slice(0, 16)}…</Typography> },
      { accessorKey: "processed_at", header: "Processed", size: 170, cell: ({ getValue }) => dateTime(getValue() as string | null) },
    ],
    [],
  );

  const errCols = useMemo<ColumnDef<ErrRow, unknown>[]>(
    () => [
      { accessorKey: "created_at", header: "When", size: 170, cell: ({ getValue }) => dateTime(getValue() as string) },
      { accessorKey: "subscription_name", header: "Subscription", size: 200, cell: ({ getValue }) => (getValue() as string) ?? "—" },
      { accessorKey: "error_type", header: "Type", size: 160, cell: ({ getValue }) => <StatusChip value="error" tone="critical" label={titleCase(getValue() as string)} /> },
      { accessorKey: "row_number", header: "Row", size: 80, meta: { numeric: true } },
      { accessorKey: "message", header: "Message", size: 460, cell: ({ getValue }) => <Typography variant="caption" noWrap title={getValue() as string} component="div">{getValue() as string}</Typography> },
      { accessorKey: "job_id", header: "Job", size: 70, meta: { numeric: true } },
      { accessorKey: "export_run_id", header: "Run", size: 70, meta: { numeric: true } },
    ],
    [],
  );

  return (
    <Box data-testid="data-management-page">
      <PageHeader
        title="Data Management"
        subtitle="Azure Cost Management export ingestion, data freshness and data quality. Reporting always reads PostgreSQL; only the actions on this page fetch new billing data."
        actions={
          canIngest ? (
            <>
              <Button variant="outlined" color="inherit" startIcon={<InsightsOutlinedIcon fontSize="small" />} data-testid="run-analytics"
                onClick={async () => {
                  try {
                    const r = await api<{ job_id: number; created: boolean }>("/ingestion/analytics", { method: "POST", params: { lookback_days: 7 } });
                    toast(r.created ? `Analytics job ${r.job_id} queued` : `Analytics job ${r.job_id} already queued`);
                    refreshAll();
                  } catch (e) {
                    toast(errorMessage(e), "error");
                  }
                }}
              >
                Re-run analytics
              </Button>
              {localMode && (
                <Button variant="outlined" color="primary" startIcon={<DownloadForOfflineOutlinedIcon fontSize="small" />} data-testid="local-export-open"
                  onClick={() => { setFormError(null); localForm.reset({ months: 3, dataset_types: ["actual", "amortized"], subscription_ids: [] }); setLocalOpen(true); }}>
                  Pull to local exports
                </Button>
              )}
              <Button variant="outlined" color="inherit" startIcon={<HistoryIcon fontSize="small" />} onClick={() => { setFormError(null); backfillForm.reset({ subscription_id: "", metric: "ActualCost", start_date: "", end_date: "" }); setBackfillOpen(true); }} data-testid="backfill-open">
                Backfill (Cost Details API)
              </Button>
              <Button variant="contained" startIcon={<CloudSyncOutlinedIcon fontSize="small" />} onClick={() => setConfirmSync({})} data-testid="sync-all">
                Synchronize Azure cost data
              </Button>
            </>
          ) : (
            <Typography variant="caption">Synchronisation requires the Administrator role.</Typography>
          )
        }
      />
      <Stack spacing={2}>
        {status.error ? (
          <ErrorState error={status.error} onRetry={() => status.refetch()} />
        ) : (
          <Paper variant="outlined" sx={{ display: "flex", flexWrap: "wrap" }} data-testid="freshness-summary">
            {[
              { label: "Overall status", value: fresh ? <StatusChip value={fresh.status} label={fresh.status_label} /> : "…", sub: fresh?.is_demo ? "Demo export files (local directory)" : "Azure Blob Storage exports" },
              { label: "Latest usage date", value: longDate(fresh?.latest_usage_date), sub: fresh?.oldest_latest_usage_date && fresh.oldest_latest_usage_date !== fresh.latest_usage_date ? `Oldest subscription: ${longDate(fresh.oldest_latest_usage_date)}` : "All subscriptions aligned" },
              { label: "Last successful ingestion", value: dateTime(fresh?.last_successful_ingestion), sub: `Last attempt ${dateTime(fresh?.last_ingestion_attempt)}` },
              { label: "Coverage", value: fresh ? `${fresh.subscriptions_with_data} / ${fresh.subscriptions_enabled}` : "…", sub: "Enabled subscriptions with data" },
              { label: "Active jobs", value: String(active), sub: active ? "Auto-refreshing every 4 s" : "No jobs running" },
            ].map((x) => (
              <Box key={x.label} sx={{ px: 2, py: 1.25, flex: 1, minWidth: 190, borderRight: `1px solid ${surface.border}` }}>
                <Typography variant="caption" component="div">
                  {x.label}
                </Typography>
                <Box sx={{ fontSize: 16, fontWeight: 600, my: 0.25 }}>{x.value}</Box>
                <Typography variant="caption" component="div">
                  {x.sub}
                </Typography>
              </Box>
            ))}
          </Paper>
        )}
        <Alert severity="info" variant="outlined" sx={{ bgcolor: "#fff" }}>
          <b>Refresh vs synchronise:</b> the header&apos;s Refresh button only reloads results from the database. &quot;Synchronize Azure cost data&quot; queues one independent job per subscription that discovers new Cost Management export runs and ingests them (idempotent — already-applied runs are skipped). {fresh?.current_period_note}
        </Alert>
        <Section title="Subscription data freshness" subtitle="Each subscription is ingested independently; a failure in one never blocks the others." noPadding testId="freshness-table-section">
          <DataTable data={subs} columns={subCols} getRowId={(r) => r.subscription_id} storageKey="dm-freshness" defaultHidden={["earliest", "last_sync_attempt_at"]} loading={status.isFetching} testId="freshness-table" />
        </Section>
        <Box>
          <Tabs value={s.tab} onChange={(_, v) => set({ tab: v })} sx={{ borderBottom: 1, borderColor: "divider", mb: 1.5 }}>
            <Tab value="jobs" label={`Ingestion jobs${active ? ` (${active} active)` : ""}`} data-testid="tab-jobs" />
            <Tab value="runs" label="Export runs" data-testid="tab-runs" />
            <Tab value="files" label="Source files" data-testid="tab-files" />
            <Tab value="errors" label="Data-quality errors" data-testid="tab-errors" />
          </Tabs>
          <Paper variant="outlined">
            {s.tab === "jobs" && (
              <DataTable
                data={jobs.data?.data ?? []}
                columns={jobCols}
                loading={jobs.isFetching}
                error={jobs.error ? errorMessage(jobs.error) : null}
                serverPaging={{ page: jobsPaging.page, pageSize: jobsPaging.size, total: jobs.data?.meta.total ?? 0, onChange: (page, size) => setJobsPaging({ page, size }) }}
                onRowClick={(j) => setJobId(j.id)}
                getRowId={(j) => String(j.id)}
                storageKey="dm-jobs"
                defaultHidden={["triggered_by", "finished_at"]}
                emptyMessage="No ingestion jobs yet."
                testId="jobs-table"
                toolbar={<Typography variant="body2" color="text.secondary">Click a job for its log and errors. Failed jobs retry automatically with backoff before needing a manual retry.</Typography>}
              />
            )}
            {s.tab === "runs" && <Pager<Run> path="/ingestion/runs" columns={runCols} storageKey="dm-runs" testId="runs-table" defaultHidden={["run_key", "days_skipped_newer"]} emptyMessage="No export runs discovered." />}
            {s.tab === "files" && <Pager<FileRow> path="/ingestion/files" columns={fileCols} storageKey="dm-files" testId="files-table" defaultHidden={["normalizer_version", "content_hash", "rows_loaded"]} emptyMessage="No source files ingested." />}
            {s.tab === "errors" && <Pager<ErrRow> path="/ingestion/errors" columns={errCols} storageKey="dm-errors" testId="errors-table" emptyMessage="No data-quality errors recorded." />}
          </Paper>
        </Box>
      </Stack>

      <ConfirmDialog
        open={!!confirmSync}
        title={confirmSync?.subscription ? `Synchronise ${confirmSync.subscription.subscription_name}` : "Synchronize Azure cost data"}
        message={
          <>
            {confirmSync?.subscription ? "A synchronisation job will be queued for this subscription." : "One synchronisation job will be queued per enabled subscription."} The worker discovers new export runs in storage and ingests them; runs that were already applied are skipped, and existing queued jobs are reused rather than duplicated.
          </>
        }
        confirmLabel="Queue synchronisation"
        busy={busy}
        testId="sync-dialog"
        onClose={() => setConfirmSync(null)}
        onConfirm={() => doSync(confirmSync?.subscription ? [confirmSync.subscription.subscription_id] : undefined)}
      />

      <FormDialog
        open={reprocessOpen !== null}
        title="Reprocess historical data"
        onClose={() => setReprocessOpen(null)}
        busy={reprocessForm.formState.isSubmitting}
        error={formError}
        submitLabel="Queue reprocessing"
        testId="reprocess-dialog"
        onSubmit={reprocessForm.handleSubmit(async (v) => {
          setFormError(null);
          try {
            const r = await api<{ job_id: number }>("/ingestion/reprocess", { method: "POST", body: { ...v, dataset_types: v.dataset_types.length ? v.dataset_types : null } });
            toast(`Reprocess job ${r.job_id} queued`);
            setReprocessOpen(null);
            refreshAll();
          } catch (e) {
            setFormError(errorMessage(e));
          }
        })}
      >
        <Typography variant="body2" color="text.secondary">
          Re-ingests every export run overlapping the range (forced). Replace-by-day semantics mean data is replaced, never duplicated, and days supplied by newer runs are preserved.
        </Typography>
        <RhfSelect control={reprocessForm.control} name="subscription_id" label="Subscription" options={subOptions} />
        <Grid container spacing={2}>
          <Grid size={{ xs: 6 }}>
            <RhfText control={reprocessForm.control} name="period_from" label="From" type="date" />
          </Grid>
          <Grid size={{ xs: 6 }}>
            <RhfText control={reprocessForm.control} name="period_to" label="To" type="date" />
          </Grid>
        </Grid>
        <RhfSelect control={reprocessForm.control} name="dataset_types" label="Datasets (empty = all)" multiple options={[{ value: "actual", label: "Actual" }, { value: "amortized", label: "Amortized" }, { value: "focus", label: "FOCUS" }]} />
      </FormDialog>

      <FormDialog
        open={backfillOpen}
        title="Backfill via Cost Details API"
        onClose={() => setBackfillOpen(false)}
        busy={backfillForm.formState.isSubmitting}
        error={formError}
        submitLabel="Queue backfill"
        testId="backfill-dialog"
        onSubmit={backfillForm.handleSubmit(async (v) => {
          setFormError(null);
          try {
            const r = await api<{ job_id: number }>("/ingestion/backfill", { method: "POST", body: v });
            toast(`Backfill job ${r.job_id} queued`);
            setBackfillOpen(false);
            refreshAll();
          } catch (e) {
            setFormError(errorMessage(e));
          }
        })}
      >
        <Alert severity="info">Supplementary to exports. The Cost Details API generates a report asynchronously (at most one month per request, subject to Microsoft rate limits). Requests are queued and de-duplicated; not available for demo subscriptions.</Alert>
        <RhfSelect control={backfillForm.control} name="subscription_id" label="Subscription" options={subOptions} />
        <RhfSelect control={backfillForm.control} name="metric" label="Dataset" options={[{ value: "ActualCost", label: "Actual cost" }, { value: "AmortizedCost", label: "Amortized cost" }]} />
        <Grid container spacing={2}>
          <Grid size={{ xs: 6 }}>
            <RhfText control={backfillForm.control} name="start_date" label="Start" type="date" />
          </Grid>
          <Grid size={{ xs: 6 }}>
            <RhfText control={backfillForm.control} name="end_date" label="End" type="date" />
          </Grid>
        </Grid>
      </FormDialog>

      <FormDialog
        open={localOpen}
        title="Pull cost data to local exports"
        onClose={() => setLocalOpen(false)}
        busy={localForm.formState.isSubmitting}
        error={formError}
        submitLabel="Queue pull"
        testId="local-export-dialog"
        onSubmit={localForm.handleSubmit(async (v) => {
          setFormError(null);
          try {
            const r = await api<{ jobs: { job_id: number; created: boolean }[]; range: [string, string]; months: number }>("/ingestion/local-export", {
              method: "POST",
              body: { months: v.months, dataset_types: v.dataset_types, subscription_ids: v.subscription_ids.length ? v.subscription_ids : null },
            });
            toast(`${r.jobs.length} job(s) queued for ${r.range[0]} → ${r.range[1]} (${r.months} month(s))`);
            setLocalOpen(false);
            refreshAll();
          } catch (e) {
            setFormError(errorMessage(e));
          }
        })}
      >
        <Alert severity="info">
          Local export mode (<code>EXPORT_SOURCE=local</code>): no storage account is needed. For each subscription, month and cost type the Cost Details API generates a CSV report; it is saved in the
          local export folder in the same layout an Azure export would use, then ingested. Re-pulling a month replaces it. Read-only — nothing is created in your subscriptions. Jobs run one at a time and
          each report can take a minute or more.
        </Alert>
        <RhfText control={localForm.control} name="months" label="Calendar months (ending with the current month)" type="number" testId="local-export-months" />
        <RhfSelect control={localForm.control} name="dataset_types" label="Cost types" multiple options={[{ value: "actual", label: "Actual cost" }, { value: "amortized", label: "Amortized cost" }]} />
        <RhfSelect control={localForm.control} name="subscription_ids" label="Subscriptions (empty = all enabled)" multiple options={subOptions.filter((o) => !subs.find((x) => x.subscription_id === o.value)?.is_demo)} />
      </FormDialog>

      <Drawer anchor="right" open={jobId !== null} onClose={() => setJobId(null)} slotProps={{ paper: { sx: { width: { xs: "100%", md: 640 } } } }}>
        <Box sx={{ p: 2 }} data-testid="job-drawer">
          <Stack direction="row" alignItems="center" sx={{ mb: 1.5 }}>
            <Typography variant="h2" sx={{ flex: 1 }}>
              Job {jobId} {detail.data ? `· ${JOB_LABEL[detail.data.job_type] ?? detail.data.job_type}` : ""}
            </Typography>
            <Tooltip title="Close">
              <IconButton onClick={() => setJobId(null)} aria-label="Close job details">
                <CloseIcon />
              </IconButton>
            </Tooltip>
          </Stack>
          {detail.error ? (
            <ErrorState error={detail.error} />
          ) : !detail.data ? (
            <LinearProgress />
          ) : (
            <Stack spacing={2}>
              <KeyValueList
                data={{
                  status: detail.data.status,
                  subscription: detail.data.subscription_name ?? "n/a",
                  attempts: `${detail.data.attempts} of ${detail.data.max_attempts}`,
                  progress: detail.data.progress?.step ?? "—",
                  started: dateTime(detail.data.started_at),
                  finished: dateTime(detail.data.finished_at),
                  triggered_by: detail.data.triggered_by,
                  parameters: detail.data.params,
                  error: detail.data.error_message,
                }}
              />
              {detail.data.result && (
                <Box>
                  <Typography variant="subtitle1" sx={{ mb: 0.5 }}>
                    Result
                  </Typography>
                  <KeyValueList data={Object.fromEntries(Object.entries(detail.data.result).filter(([k]) => k !== "outcomes"))} />
                </Box>
              )}
              <Box>
                <Typography variant="subtitle1" sx={{ mb: 0.5 }}>
                  Log ({detail.data.logs.length})
                </Typography>
                <Stack spacing={0.5} sx={{ maxHeight: 320, overflowY: "auto" }}>
                  {detail.data.logs.length === 0 && <Typography variant="caption">No log entries (no new runs processed).</Typography>}
                  {detail.data.logs.map((l, i) => (
                    <Box key={i} sx={{ p: 1, border: `1px solid ${surface.border}`, borderRadius: 1, bgcolor: l.level === "error" ? "#fdeeee" : "#fff" }}>
                      <Typography variant="caption" component="div">
                        {dateTime(l.created_at)} · {l.operation} · {l.level}
                      </Typography>
                      <Typography variant="body2">{l.message}</Typography>
                    </Box>
                  ))}
                </Stack>
              </Box>
              <Box>
                <Typography variant="subtitle1" sx={{ mb: 0.5 }}>
                  Errors ({detail.data.errors.length})
                </Typography>
                {detail.data.errors.length === 0 ? (
                  <Typography variant="caption">No errors recorded for this job.</Typography>
                ) : (
                  detail.data.errors.map((e) => (
                    <Typography key={e.id} variant="body2" color="error" sx={{ mb: 0.5 }}>
                      [{e.error_type}] {e.row_number ? `row ${e.row_number}: ` : ""}
                      {e.message}
                    </Typography>
                  ))
                )}
              </Box>
            </Stack>
          )}
        </Box>
      </Drawer>
    </Box>
  );
}

export default function DataManagementPage() {
  return (
    <ToastProvider>
      <DataInner />
    </ToastProvider>
  );
}
