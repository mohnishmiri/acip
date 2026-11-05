"use client";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Box, Button, Grid, IconButton, Link as MuiLink, MenuItem, Select, Stack, Tab, Tabs, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { PageHeader } from "@/components/common/PageHeader";
import { Section } from "@/components/common/Section";
import { SeverityChip, StatusChip } from "@/components/common/StatusChip";
import { useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { useUrlState } from "@/hooks/useUrlState";
import { api } from "@/lib/api";
import { dateTime, titleCase } from "@/lib/format";
import { useApi, useFilterOptions } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { ConfirmDialog, errorMessage, FormDialog, RhfSelect, RhfSwitch, RhfText, ToastProvider, useCan, useToast } from "@/features/admin/ui";

interface Notification {
  id: number;
  type: string;
  severity: string;
  title: string;
  message: string;
  link: string | null;
  is_read: boolean;
  created_at: string;
  delivery_status: string;
  is_demo: boolean;
}
interface AlertRule {
  id: number;
  name: string;
  alert_type: string;
  min_severity: string | null;
  filters: { environment_groups?: string[]; service_categories?: string[] };
  params: { min_monthly_savings?: number };
  channels: string[];
  cooldown_hours: number;
  enabled: boolean;
}

const TYPES = [
  { value: "anomaly", label: "Cost anomaly" },
  { value: "budget_threshold", label: "Budget threshold exceeded" },
  { value: "budget_forecast", label: "Forecast expected to exceed budget" },
  { value: "ingestion_failure", label: "Failed ingestion" },
  { value: "data_delay", label: "Delayed subscription data" },
  { value: "savings_opportunity", label: "Potential savings opportunity" },
];
const TYPE_LABEL = Object.fromEntries(TYPES.map((t) => [t.value, t.label]));
const SEVERITIES = ["informational", "low", "medium", "high", "critical"];

const ruleSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  alert_type: z.enum(["anomaly", "budget_threshold", "budget_forecast", "ingestion_failure", "data_delay", "savings_opportunity"]),
  min_severity: z.string(),
  channels: z.array(z.enum(["in_app", "teams", "email"])).min(1, "Select at least one channel"),
  cooldown_hours: z.number({ error: "Enter hours" }).int("Whole hours").min(0).max(720),
  enabled: z.boolean(),
  environment_groups: z.array(z.string()),
  service_categories: z.array(z.string()),
  min_monthly_savings: z.number({ error: "Enter an amount" }).min(0),
});
type RuleValues = z.infer<typeof ruleSchema>;

function RuleForm({ open, rule, onClose, onSaved }: { open: boolean; rule: AlertRule | null; onClose: () => void; onSaved: (m: string) => void }) {
  const opts = useFilterOptions();
  const [error, setError] = useState<string | null>(null);
  const defaults = useMemo<RuleValues>(
    () => ({
      name: rule?.name ?? "",
      alert_type: (rule?.alert_type as RuleValues["alert_type"]) ?? "anomaly",
      min_severity: rule?.min_severity ?? "medium",
      channels: (rule?.channels as RuleValues["channels"]) ?? ["in_app"],
      cooldown_hours: rule?.cooldown_hours ?? 24,
      enabled: rule?.enabled ?? true,
      environment_groups: rule?.filters?.environment_groups ?? [],
      service_categories: rule?.filters?.service_categories ?? [],
      min_monthly_savings: rule?.params?.min_monthly_savings ?? 500,
    }),
    [rule],
  );
  const { control, handleSubmit, reset, formState } = useForm<RuleValues>({ resolver: zodResolver(ruleSchema), defaultValues: defaults });
  useEffect(() => {
    if (open) {
      reset(defaults);
      setError(null);
    }
  }, [open, defaults, reset]);
  const type = useWatch({ control, name: "alert_type" });
  const channels = useWatch({ control, name: "channels" });
  const submit = handleSubmit(async (v) => {
    setError(null);
    const body = {
      name: v.name,
      alert_type: v.alert_type,
      min_severity: v.alert_type === "anomaly" ? v.min_severity || null : null,
      channels: v.channels,
      cooldown_hours: v.cooldown_hours,
      enabled: v.enabled,
      filters: { ...(v.environment_groups.length ? { environment_groups: v.environment_groups } : {}), ...(v.service_categories.length ? { service_categories: v.service_categories } : {}) },
      params: v.alert_type === "savings_opportunity" ? { min_monthly_savings: v.min_monthly_savings } : {},
    };
    try {
      if (rule) await api(`/alert-rules/${rule.id}`, { method: "PUT", body });
      else await api("/alert-rules", { method: "POST", body });
      onSaved(rule ? "Alert rule updated" : "Alert rule created");
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  return (
    <FormDialog open={open} title={rule ? `Edit alert rule — ${rule.name}` : "New alert rule"} onClose={onClose} onSubmit={submit} busy={formState.isSubmitting} error={error} testId="alert-rule-dialog">
      <RhfText control={control} name="name" label="Rule name" required testId="alert-rule-name" />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 7 }}>
          <RhfSelect control={control} name="alert_type" label="Alert type" options={TYPES} testId="alert-rule-type" />
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <RhfSelect control={control} name="min_severity" label="Minimum severity" options={SEVERITIES.map((s) => ({ value: s, label: titleCase(s) }))} disabled={type !== "anomaly"} helperText={type !== "anomaly" ? "Applies to anomaly alerts only" : undefined} />
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          <RhfSelect control={control} name="channels" label="Channels" multiple options={[{ value: "in_app", label: "In-app" }, { value: "teams", label: "Microsoft Teams (future)" }, { value: "email", label: "Email (future)" }]} />
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <RhfText control={control} name="cooldown_hours" label="Cooldown (hours)" type="number" helperText="Minimum hours between repeat notifications" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSelect control={control} name="environment_groups" label="Environments (optional)" multiple options={(opts.data?.environment_groups ?? []).map((g) => ({ value: g.code, label: g.name }))} helperText="Empty = all environments" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSelect control={control} name="service_categories" label="Azure services (optional)" multiple options={(opts.data?.service_categories ?? []).map((c) => ({ value: c, label: c }))} helperText="Empty = all services" />
        </Grid>
        {type === "savings_opportunity" && (
          <Grid size={{ xs: 12, md: 6 }}>
            <RhfText control={control} name="min_monthly_savings" label="Minimum estimated monthly savings" type="number" />
          </Grid>
        )}
      </Grid>
      {channels?.some((c) => c !== "in_app") && (
        <Alert severity="info">Microsoft Teams and email delivery are extension points and are not enabled in this release. Notifications are always stored in-app.</Alert>
      )}
      <RhfSwitch control={control} name="enabled" label="Rule enabled" />
    </FormDialog>
  );
}

function AlertsInner() {
  const link = useLinkWithFilters();
  const toast = useToast();
  const qc = useQueryClient();
  const canManage = useCan("manage_alerts");
  const [s, set] = useUrlState({ tab: "notifications", read: "all", type: "", page: "1" });
  const page = Number(s.page) || 1;
  const notes = useApi<{ data: Notification[]; meta: { total: number; unread: number; page: number; page_size: number } }>("/notifications", {
    unread_only: s.read === "unread" ? true : undefined,
    notification_type: s.type ? [s.type] : undefined,
    page,
    page_size: 50,
  });
  const rules = useApi<AlertRule[]>("/alert-rules");
  const [editing, setEditing] = useState<AlertRule | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [deleting, setDeleting] = useState<AlertRule | null>(null);
  const invalidate = () => qc.invalidateQueries({ predicate: (q) => typeof q.queryKey[0] === "string" && ["/notifications", "/alert-rules"].some((p) => (q.queryKey[0] as string).startsWith(p)) });
  const markRead = async (ids?: number[]) => {
    try {
      await api("/notifications/read", { method: "POST", body: ids ? { ids } : {} });
      invalidate();
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  const noteCols = useMemo<ColumnDef<Notification, unknown>[]>(
    () => [
      { accessorKey: "severity", header: "Severity", size: 120, cell: ({ getValue }) => <SeverityChip severity={getValue() as string} /> },
      { accessorKey: "type", header: "Type", size: 200, cell: ({ getValue }) => TYPE_LABEL[getValue() as string] ?? titleCase(getValue() as string) },
      {
        accessorKey: "title",
        header: "Notification",
        size: 420,
        enableHiding: false,
        cell: ({ row }) => (
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="body2" noWrap sx={{ fontWeight: row.original.is_read ? 400 : 700 }} title={row.original.title}>
              {row.original.title}
            </Typography>
            <Typography variant="caption" noWrap component="div" title={row.original.message}>
              {row.original.message}
            </Typography>
          </Box>
        ),
      },
      { accessorKey: "created_at", header: "Raised", size: 170, cell: ({ getValue }) => dateTime(getValue() as string) },
      { accessorKey: "is_read", header: "State", size: 90, cell: ({ getValue }) => (getValue() ? <StatusChip value="read" tone="neutral" label="Read" /> : <StatusChip value="unread" tone="info" label="Unread" />) },
      { accessorKey: "delivery_status", header: "Delivery", size: 110, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
      {
        id: "actions",
        header: "",
        size: 170,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) => (
          <Stack direction="row" spacing={1} alignItems="center">
            {row.original.link && (
              <MuiLink component={Link} href={link(row.original.link)} underline="hover" sx={{ fontWeight: 600, fontSize: 12.5 }} onClick={() => !row.original.is_read && markRead([row.original.id])}>
                Investigate
              </MuiLink>
            )}
            {!row.original.is_read && (
              <Button size="small" onClick={() => markRead([row.original.id])}>
                Mark read
              </Button>
            )}
          </Stack>
        ),
      },
    ],
    [link], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const ruleCols = useMemo<ColumnDef<AlertRule, unknown>[]>(
    () => [
      { accessorKey: "name", header: "Rule", size: 280, enableHiding: false, cell: ({ getValue }) => <Typography variant="body2" sx={{ fontWeight: 600 }}>{getValue() as string}</Typography> },
      { accessorKey: "alert_type", header: "Type", size: 230, cell: ({ getValue }) => TYPE_LABEL[getValue() as string] ?? (getValue() as string) },
      { accessorKey: "min_severity", header: "Min severity", size: 120, cell: ({ getValue }) => (getValue() ? <SeverityChip severity={getValue() as string} /> : "—") },
      { id: "filters", header: "Filters", size: 240, accessorFn: (r) => [...(r.filters.environment_groups ?? []), ...(r.filters.service_categories ?? [])].join(", "), cell: ({ getValue }) => (getValue() as string) || "All" },
      { id: "channels", header: "Channels", size: 160, accessorFn: (r) => r.channels.map((c) => (c === "in_app" ? "In-app" : titleCase(c))).join(", ") },
      { accessorKey: "cooldown_hours", header: "Cooldown", size: 100, meta: { numeric: true }, cell: ({ getValue }) => `${getValue()} h` },
      { accessorKey: "enabled", header: "Status", size: 100, cell: ({ getValue }) => (getValue() ? <StatusChip value="ok" label="Enabled" /> : <StatusChip value="disabled" />) },
      {
        id: "actions",
        header: "",
        size: 90,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) =>
          canManage ? (
            <Stack direction="row">
              <Tooltip title="Edit">
                <IconButton aria-label={`Edit ${row.original.name}`} onClick={() => { setEditing(row.original); setFormOpen(true); }} data-testid={`alert-rule-edit-${row.original.id}`}>
                  <EditOutlinedIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Delete">
                <IconButton aria-label={`Delete ${row.original.name}`} onClick={() => setDeleting(row.original)}>
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          ) : null,
      },
    ],
    [canManage],
  );

  return (
    <Box data-testid="alerts-page">
      <PageHeader
        title="Alerts & Notifications"
        subtitle="In-app alerts for cost anomalies, budget thresholds, forecasts, ingestion failures, delayed data and savings opportunities. Each unresolved issue notifies once (de-duplicated)."
        actions={
          s.tab === "rules" && canManage ? (
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => { setEditing(null); setFormOpen(true); }} data-testid="alert-rule-new">
              New alert rule
            </Button>
          ) : s.tab === "notifications" ? (
            <Button variant="outlined" color="inherit" startIcon={<DoneAllIcon fontSize="small" />} onClick={() => markRead()} disabled={!notes.data?.meta.unread} data-testid="notifications-mark-all">
              Mark all read
            </Button>
          ) : undefined
        }
      />
      <Tabs value={s.tab} onChange={(_, v) => set({ tab: v, page: "1" })} sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
        <Tab value="notifications" label={`Notifications${notes.data ? ` (${notes.data.meta.unread} unread)` : ""}`} data-testid="tab-notifications" />
        <Tab value="rules" label="Alert rules" data-testid="tab-alert-rules" />
      </Tabs>
      {s.tab === "notifications" ? (
        <Section title="Notifications" subtitle={notes.data ? `${notes.data.meta.total} notifications` : " "} noPadding testId="notifications-section">
          <DataTable
            data={notes.data?.data ?? []}
            columns={noteCols}
            loading={notes.isFetching}
            error={notes.error ? errorMessage(notes.error) : null}
            getRowId={(r) => String(r.id)}
            storageKey="notifications"
            defaultHidden={["delivery_status"]}
            serverPaging={{ page, pageSize: 50, total: notes.data?.meta.total ?? 0, onChange: (p) => set({ page: String(p) }) }}
            emptyMessage="No notifications."
            testId="notifications-table"
            toolbar={
              <Stack direction="row" spacing={1} alignItems="center">
                <ToggleButtonGroup size="small" exclusive value={s.read} onChange={(_, v) => v && set({ read: v, page: "1" })} aria-label="Read filter">
                  <ToggleButton value="all">All</ToggleButton>
                  <ToggleButton value="unread">Unread</ToggleButton>
                </ToggleButtonGroup>
                <Select size="small" displayEmpty value={s.type} onChange={(e) => set({ type: e.target.value, page: "1" })} sx={{ minWidth: 220, "& .MuiSelect-select": { py: "4px" } }} inputProps={{ "aria-label": "Notification type" }} data-testid="notifications-type-filter">
                  <MenuItem value="">All types</MenuItem>
                  {TYPES.map((t) => (
                    <MenuItem key={t.value} value={t.value}>
                      {t.label}
                    </MenuItem>
                  ))}
                </Select>
              </Stack>
            }
          />
        </Section>
      ) : (
        <Stack spacing={2}>
          <Alert severity="info" variant="outlined" sx={{ bgcolor: "#fff" }}>
            Alert rules decide which detections create notifications. Anomaly detection thresholds themselves are configured under Administration → Anomaly rules. Microsoft Teams and email are designed-in extension points; this release delivers in-app only.
          </Alert>
          <Section title="Alert rules" noPadding testId="alert-rules-section">
            <DataTable data={rules.data ?? []} columns={ruleCols} loading={rules.isFetching} error={rules.error ? errorMessage(rules.error) : null} getRowId={(r) => String(r.id)} storageKey="alert-rules" testId="alert-rules-table" />
          </Section>
        </Stack>
      )}
      <RuleForm open={formOpen} rule={editing} onClose={() => setFormOpen(false)} onSaved={(m) => { setFormOpen(false); toast(m); invalidate(); }} />
      <ConfirmDialog
        open={!!deleting}
        title="Delete alert rule"
        message={<>Delete <b>{deleting?.name}</b>? Existing notifications are kept.</>}
        confirmLabel="Delete"
        danger
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          if (!deleting) return;
          try {
            await api(`/alert-rules/${deleting.id}`, { method: "DELETE" });
            toast("Alert rule deleted");
            invalidate();
          } catch (e) {
            toast(errorMessage(e), "error");
          } finally {
            setDeleting(null);
          }
        }}
      />
    </Box>
  );
}

export default function AlertsPage() {
  return (
    <ToastProvider>
      <AlertsInner />
    </ToastProvider>
  );
}
