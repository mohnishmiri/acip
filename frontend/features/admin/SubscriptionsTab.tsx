"use client";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import { zodResolver } from "@hookform/resolvers/zod";
import { Box, Button, Grid, IconButton, Stack, Switch, Tooltip, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";
import { Section } from "@/components/common/Section";
import { StatusChip } from "@/components/common/StatusChip";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useApi, useFilterOptions } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { useMutate } from "./hooks";
import { ConfirmDialog, errorMessage, FormDialog, KeyValueList, RhfSelect, RhfSwitch, RhfText, useCan } from "./ui";

export interface ExportDef {
  id?: number;
  dataset_type: "actual" | "amortized" | "focus";
  export_name: string;
  container: string;
  root_folder_path: string;
  storage_account_url: string | null;
  enabled: boolean;
  blob_prefix?: string;
  last_discovery_at?: string | null;
  last_discovery_error?: string | null;
}
export interface Subscription {
  id: number;
  subscription_id: string;
  subscription_name: string;
  application_id: number | null;
  application_name: string | null;
  environment: string | null;
  environment_name: string | null;
  tenant_id: string | null;
  billing_currency: string;
  enabled: boolean;
  is_demo: boolean;
  connection_status: string;
  auth_status: string;
  cost_api_status: string;
  storage_status: string;
  last_connection_test_at: string | null;
  connection_details: { steps?: Record<string, { status: string; message: string; remediation?: string | null }>; overall?: string; tested_at?: string } | null;
  last_successful_sync_at: string | null;
  last_sync_attempt_at: string | null;
  last_sync_error: string | null;
  exports: ExportDef[];
}

const GUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const ENVIRONMENTS = [
  { value: "production", label: "Production" },
  { value: "non_production", label: "Non-Production" },
  { value: "development", label: "Development" },
  { value: "testing", label: "Testing" },
  { value: "uat", label: "UAT" },
  { value: "shared", label: "Shared Services" },
  { value: "unallocated", label: "Unallocated" },
];

const schema = z.object({
  subscription_id: z.string().trim().regex(GUID, "Subscription ID must be a GUID"),
  subscription_name: z.string().trim().min(1, "Name is required").max(200),
  application_id: z.string(),
  environment: z.enum(["production", "non_production", "development", "testing", "uat", "shared", "unallocated"]),
  tenant_id: z.string().trim().refine((v) => v === "" || GUID.test(v), "Tenant ID must be a GUID"),
  billing_currency: z.string().trim().regex(/^[A-Za-z]{3}$/, "3-letter currency code"),
  enabled: z.boolean(),
  exports: z.array(
    z.object({
      dataset_type: z.enum(["actual", "amortized", "focus"]),
      export_name: z.string().trim().min(1, "Required").max(200),
      container: z.string().trim().min(3, "3–63 characters").max(63),
      root_folder_path: z.string().trim().max(500),
      storage_account_url: z.string().trim().max(500),
      enabled: z.boolean(),
    }),
  ),
});
type Values = z.infer<typeof schema>;

function SubscriptionForm({ open, sub, onClose, onSaved }: { open: boolean; sub: Subscription | null; onClose: () => void; onSaved: () => void }) {
  const opts = useFilterOptions();
  const [error, setError] = useState<string | null>(null);
  const defaults = useMemo<Values>(
    () => ({
      subscription_id: sub?.subscription_id ?? "",
      subscription_name: sub?.subscription_name ?? "",
      application_id: sub?.application_id ? String(sub.application_id) : "",
      environment: (sub?.environment as Values["environment"]) ?? "production",
      tenant_id: sub?.tenant_id ?? "",
      billing_currency: sub?.billing_currency ?? "USD",
      enabled: sub?.enabled ?? true,
      exports: (sub?.exports ?? []).map((e) => ({ dataset_type: e.dataset_type, export_name: e.export_name, container: e.container, root_folder_path: e.root_folder_path ?? "", storage_account_url: e.storage_account_url ?? "", enabled: e.enabled })),
    }),
    [sub],
  );
  const { control, handleSubmit, reset, formState } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: defaults });
  const exportsArr = useFieldArray({ control, name: "exports" });
  useEffect(() => {
    if (open) {
      reset(defaults);
      setError(null);
    }
  }, [open, defaults, reset]);

  const submit = handleSubmit(async (v) => {
    setError(null);
    const body = {
      subscription_name: v.subscription_name,
      application_id: v.application_id ? Number(v.application_id) : null,
      environment: v.environment,
      tenant_id: v.tenant_id || null,
      billing_currency: v.billing_currency.toUpperCase(),
      enabled: v.enabled,
      // new subscriptions without exports get the platform defaults (actual + amortized)
      exports: v.exports.length ? v.exports.map((e) => ({ ...e, storage_account_url: e.storage_account_url || null })) : sub ? [] : null,
    };
    try {
      if (sub) await api(`/admin/subscriptions/${sub.subscription_id}`, { method: "PUT", body });
      else await api("/admin/subscriptions", { method: "POST", body: { ...body, subscription_id: v.subscription_id.toLowerCase() } });
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  return (
    <FormDialog open={open} title={sub ? `Edit subscription — ${sub.subscription_name}` : "Register subscription"} onClose={onClose} onSubmit={submit} busy={formState.isSubmitting} error={error} maxWidth="md" testId="subscription-dialog">
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfText control={control} name="subscription_id" label="Subscription ID" required disabled={!!sub} placeholder="00000000-0000-0000-0000-000000000000" testId="subscription-id" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfText control={control} name="subscription_name" label="Subscription name" required testId="subscription-name" />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <RhfSelect control={control} name="application_id" label="Application" options={[{ value: "", label: "— None (unallocated) —" }, ...(opts.data?.applications ?? []).map((a) => ({ value: String(a.id), label: a.name }))]} />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <RhfSelect control={control} name="environment" label="Environment" options={ENVIRONMENTS} />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <RhfText control={control} name="billing_currency" label="Billing currency" />
        </Grid>
        <Grid size={{ xs: 12, md: 8 }}>
          <RhfText control={control} name="tenant_id" label="Tenant ID (optional)" helperText="Defaults to AZURE_TENANT_ID of the collection service principal" />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <RhfSwitch control={control} name="enabled" label="Enabled for collection" />
        </Grid>
      </Grid>
      <Box>
        <Stack direction="row" alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle1" sx={{ flex: 1 }}>
            Cost Management export definitions
          </Typography>
          <Button size="small" startIcon={<AddIcon />} onClick={() => exportsArr.append({ dataset_type: "actual", export_name: "acip-actual-daily", container: "cost-exports", root_folder_path: "", storage_account_url: "", enabled: true })}>
            Add export
          </Button>
        </Stack>
        <Typography variant="caption" component="div" sx={{ mb: 1 }}>
          Exports are created by an administrator or IaC; the platform only reads their output (least privilege). Leave empty on a new subscription to use the default actual + amortized exports. Storage account URL empty = AZURE_STORAGE_ACCOUNT_URL.
        </Typography>
        <Stack spacing={1.5}>
          {exportsArr.fields.map((f, i) => (
            <Grid container spacing={1} key={f.id} alignItems="flex-start" sx={{ p: 1, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
              <Grid size={{ xs: 12, md: 2 }}>
                <RhfSelect control={control} name={`exports.${i}.dataset_type`} label="Dataset" options={[{ value: "actual", label: "Actual" }, { value: "amortized", label: "Amortized" }, { value: "focus", label: "FOCUS" }]} />
              </Grid>
              <Grid size={{ xs: 12, md: 3 }}>
                <RhfText control={control} name={`exports.${i}.export_name`} label="Export name" />
              </Grid>
              <Grid size={{ xs: 12, md: 2 }}>
                <RhfText control={control} name={`exports.${i}.container`} label="Container" />
              </Grid>
              <Grid size={{ xs: 12, md: 4 }}>
                <RhfText control={control} name={`exports.${i}.root_folder_path`} label="Root folder path" />
              </Grid>
              <Grid size={{ xs: 12, md: 1 }} sx={{ display: "flex", justifyContent: "flex-end" }}>
                <Tooltip title="Remove export">
                  <IconButton onClick={() => exportsArr.remove(i)} aria-label="Remove export">
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Grid>
              <Grid size={{ xs: 12, md: 9 }}>
                <RhfText control={control} name={`exports.${i}.storage_account_url`} label="Storage account URL (optional)" />
              </Grid>
              <Grid size={{ xs: 12, md: 3 }}>
                <RhfSwitch control={control} name={`exports.${i}.enabled`} label="Enabled" />
              </Grid>
            </Grid>
          ))}
        </Stack>
      </Box>
    </FormDialog>
  );
}

export function SubscriptionsTab() {
  const q = useApi<Subscription[]>("/admin/subscriptions");
  const canAdmin = useCan("admin");
  const mutate = useMutate();
  const [editing, setEditing] = useState<Subscription | null>(null);
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState<Subscription | null>(null);

  const columns = useMemo<ColumnDef<Subscription, unknown>[]>(
    () => [
      { accessorKey: "subscription_name", header: "Subscription", size: 250, enableHiding: false, cell: ({ row }) => <Box><Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{row.original.subscription_name}{row.original.is_demo ? " (demo)" : ""}</Typography><Typography variant="caption" component="div" noWrap>{row.original.subscription_id}</Typography></Box> },
      { accessorKey: "application_name", header: "Application", size: 140, cell: ({ getValue }) => (getValue() as string) ?? <StatusChip value="unallocated" label="Unallocated" /> },
      { accessorKey: "environment_name", header: "Environment", size: 130 },
      { accessorKey: "tenant_id", header: "Tenant ID", size: 290, cell: ({ getValue }) => <Typography variant="caption">{(getValue() as string) ?? "—"}</Typography> },
      { accessorKey: "billing_currency", header: "Currency", size: 90 },
      { id: "exports", header: "Exports", size: 160, accessorFn: (r) => r.exports.map((e) => e.dataset_type).join(", "), cell: ({ getValue }) => (getValue() as string) || "—" },
      { accessorKey: "connection_status", header: "Connection", size: 130, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
      { accessorKey: "last_successful_sync_at", header: "Last successful sync", size: 180, cell: ({ getValue }) => dateTime(getValue() as string | null) },
      { accessorKey: "last_sync_error", header: "Last sync error", size: 240, cell: ({ getValue }) => (getValue() ? <Typography variant="caption" color="error" noWrap title={getValue() as string} component="div">{getValue() as string}</Typography> : "—") },
      {
        accessorKey: "enabled",
        header: "Enabled",
        size: 90,
        cell: ({ row }) => (
          <Switch
            size="small"
            checked={row.original.enabled}
            disabled={!canAdmin}
            inputProps={{ "aria-label": `Enable ${row.original.subscription_name}` }}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => mutate(() => api(`/admin/subscriptions/${row.original.subscription_id}`, { method: "PUT", body: { enabled: e.target.checked } }), e.target.checked ? "Subscription enabled" : "Subscription disabled", "/ingestion")}
          />
        ),
      },
      {
        id: "actions",
        header: "",
        size: 90,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) =>
          canAdmin ? (
            <Stack direction="row">
              <Tooltip title="Edit">
                <IconButton aria-label={`Edit ${row.original.subscription_name}`} onClick={(e) => { e.stopPropagation(); setEditing(row.original); setOpen(true); }} data-testid={`subscription-edit-${row.original.subscription_id}`}>
                  <EditOutlinedIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Delete (only possible before data is ingested)">
                <IconButton aria-label={`Delete ${row.original.subscription_name}`} onClick={(e) => { e.stopPropagation(); setDeleting(row.original); }}>
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          ) : null,
      },
    ],
    [canAdmin, mutate],
  );

  return (
    <Section
      title="Registered subscriptions"
      subtitle="Subscriptions are configuration, not code: add future subscriptions here or through AZURE_SUBSCRIPTIONS_CONFIG. Disable instead of deleting to keep history."
      noPadding
      testId="subscriptions-section"
      actions={canAdmin ? <Button variant="contained" startIcon={<AddIcon />} onClick={() => { setEditing(null); setOpen(true); }} data-testid="subscription-new">Register subscription</Button> : undefined}
    >
      <DataTable
        data={q.data ?? []}
        columns={columns}
        loading={q.isFetching}
        error={q.error ? errorMessage(q.error) : null}
        getRowId={(r) => r.subscription_id}
        storageKey="admin-subscriptions"
        defaultHidden={["tenant_id", "last_sync_error"]}
        testId="subscriptions-table"
        renderSubRow={(s) => (
          <Stack spacing={1}>
            <Typography variant="subtitle2">Export definitions</Typography>
            {s.exports.length === 0 ? (
              <Typography variant="caption">None configured.</Typography>
            ) : (
              s.exports.map((e) => (
                <KeyValueList
                  key={`${e.dataset_type}-${e.export_name}`}
                  data={{ dataset: e.dataset_type, export_name: e.export_name, container: e.container, blob_prefix: e.blob_prefix, storage_account: e.storage_account_url ?? "AZURE_STORAGE_ACCOUNT_URL", enabled: e.enabled, last_discovery: dateTime(e.last_discovery_at ?? null), last_discovery_error: e.last_discovery_error ?? null }}
                />
              ))
            )}
          </Stack>
        )}
      />
      <SubscriptionForm open={open} sub={editing} onClose={() => setOpen(false)} onSaved={() => { setOpen(false); mutate(async () => undefined, editing ? "Subscription updated" : "Subscription registered", "/ingestion"); }} />
      <ConfirmDialog
        open={!!deleting}
        title="Delete subscription"
        message={<>Delete <b>{deleting?.subscription_name}</b>? Subscriptions with ingested cost data cannot be deleted — disable them instead to preserve history and the audit trail.</>}
        confirmLabel="Delete"
        danger
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          if (deleting) await mutate(() => api(`/admin/subscriptions/${deleting.subscription_id}`, { method: "DELETE" }), "Subscription deleted");
          setDeleting(null);
        }}
      />
    </Section>
  );
}
