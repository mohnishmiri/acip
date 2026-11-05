"use client";
import AddIcon from "@mui/icons-material/Add";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import ReplayIcon from "@mui/icons-material/Replay";
import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Box, Button, Grid, IconButton, Paper, Stack, Tooltip, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Section } from "@/components/common/Section";
import { StatusChip } from "@/components/common/StatusChip";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { useApi, useFilterOptions } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { surface } from "@/styles/tokens";
import { useMutate } from "./hooks";
import { ConfirmDialog, errorMessage, FormDialog, RhfSelect, RhfSwitch, RhfText, useCan } from "./ui";

interface TagMapping {
  id: number;
  tag_key: string;
  tag_value: string | null;
  target_dimension: string;
  target_value: string | null;
  priority: number;
  enabled: boolean;
  description: string | null;
}
interface AppMapping {
  id: number;
  match_type: string;
  pattern: string;
  subscription_id: string | null;
  application_id: number | null;
  environment: string | null;
  allocation_status: string;
  priority: number;
  enabled: boolean;
  description: string | null;
}
interface Setting {
  key: string;
  value: unknown;
  default: unknown;
  description: string;
}

const DIMENSIONS = ["application", "environment", "owner", "cost_center", "project", "team", "business_unit", "workload"];
const SOURCE_LABEL: Record<string, string> = { resource_group_rule: "Resource-group / resource rules", subscription: "Subscription mapping", resource_tag: "Resource tags" };

const tagSchema = z.object({
  tag_key: z.string().trim().min(1, "Tag key is required").max(200),
  tag_value: z.string().max(400),
  target_dimension: z.enum(["application", "environment", "owner", "cost_center", "project", "team", "business_unit", "workload"]),
  target_value: z.string().max(400),
  priority: z.number({ error: "Enter a number" }).int().min(0).max(10000),
  enabled: z.boolean(),
  description: z.string().max(2000),
});
type TagValues = z.infer<typeof tagSchema>;

const appSchema = z
  .object({
    match_type: z.enum(["resource_group", "resource_id"]),
    pattern: z.string().trim().min(1, "Pattern is required").max(500),
    subscription_id: z.string(),
    application_id: z.string(),
    environment: z.string(),
    allocation_status: z.enum(["allocated", "shared", "unallocated"]),
    priority: z.number({ error: "Enter a number" }).int().min(0).max(10000),
    enabled: z.boolean(),
    description: z.string().max(2000),
  })
  .refine((v) => v.allocation_status !== "allocated" || v.application_id !== "" || v.environment !== "", { path: ["application_id"], message: "An allocated rule must set an application or environment" });
type AppValues = z.infer<typeof appSchema>;

function TagForm({ open, item, onClose, onSaved }: { open: boolean; item: TagMapping | null; onClose: () => void; onSaved: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const defaults = useMemo<TagValues>(() => ({ tag_key: item?.tag_key ?? "", tag_value: item?.tag_value ?? "", target_dimension: (item?.target_dimension as TagValues["target_dimension"]) ?? "owner", target_value: item?.target_value ?? "", priority: item?.priority ?? 100, enabled: item?.enabled ?? true, description: item?.description ?? "" }), [item]);
  const { control, handleSubmit, reset, formState } = useForm<TagValues>({ resolver: zodResolver(tagSchema), defaultValues: defaults });
  useEffect(() => {
    if (open) {
      reset(defaults);
      setError(null);
    }
  }, [open, defaults, reset]);
  const submit = handleSubmit(async (v) => {
    const body = { ...v, tag_value: v.tag_value || null, target_value: v.target_value || null, description: v.description || null };
    try {
      if (item) await api(`/admin/tag-mappings/${item.id}`, { method: "PUT", body });
      else await api("/admin/tag-mappings", { method: "POST", body });
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  return (
    <FormDialog open={open} title={item ? "Edit tag mapping" : "New tag mapping"} onClose={onClose} onSubmit={submit} busy={formState.isSubmitting} error={error} testId="tag-mapping-dialog">
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfText control={control} name="tag_key" label="Tag key (case-insensitive)" required testId="tag-key" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfText control={control} name="tag_value" label="Tag value (optional)" helperText="Empty = any value" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSelect control={control} name="target_dimension" label="Maps to dimension" options={DIMENSIONS.map((d) => ({ value: d, label: titleCase(d) }))} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfText control={control} name="target_value" label="Target value (optional)" helperText="Empty = use the tag's value" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfText control={control} name="priority" label="Priority (lower first)" type="number" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSwitch control={control} name="enabled" label="Enabled" />
        </Grid>
      </Grid>
      <RhfText control={control} name="description" label="Description" multiline />
    </FormDialog>
  );
}

function AppMappingForm({ open, item, onClose, onSaved }: { open: boolean; item: AppMapping | null; onClose: () => void; onSaved: () => void }) {
  const opts = useFilterOptions();
  const [error, setError] = useState<string | null>(null);
  const defaults = useMemo<AppValues>(
    () => ({
      match_type: (item?.match_type as AppValues["match_type"]) ?? "resource_group",
      pattern: item?.pattern ?? "",
      subscription_id: item?.subscription_id ?? "",
      application_id: item?.application_id ? String(item.application_id) : "",
      environment: item?.environment ?? "",
      allocation_status: (item?.allocation_status as AppValues["allocation_status"]) ?? "allocated",
      priority: item?.priority ?? 100,
      enabled: item?.enabled ?? true,
      description: item?.description ?? "",
    }),
    [item],
  );
  const { control, handleSubmit, reset, formState } = useForm<AppValues>({ resolver: zodResolver(appSchema), defaultValues: defaults });
  useEffect(() => {
    if (open) {
      reset(defaults);
      setError(null);
    }
  }, [open, defaults, reset]);
  const submit = handleSubmit(async (v) => {
    const body = { ...v, subscription_id: v.subscription_id || null, application_id: v.application_id ? Number(v.application_id) : null, environment: v.environment || null, description: v.description || null };
    try {
      if (item) await api(`/admin/application-mappings/${item.id}`, { method: "PUT", body });
      else await api("/admin/application-mappings", { method: "POST", body });
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  return (
    <FormDialog open={open} title={item ? "Edit resource-group mapping" : "New resource-group mapping"} onClose={onClose} onSubmit={submit} busy={formState.isSubmitting} error={error} maxWidth="md" testId="app-mapping-dialog">
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 4 }}>
          <RhfSelect control={control} name="match_type" label="Match on" options={[{ value: "resource_group", label: "Resource group" }, { value: "resource_id", label: "Resource ID" }]} />
        </Grid>
        <Grid size={{ xs: 12, md: 8 }}>
          <RhfText control={control} name="pattern" label="Pattern (case-insensitive glob, e.g. rg-hub-*)" required testId="app-mapping-pattern" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSelect control={control} name="subscription_id" label="Subscription (optional)" options={[{ value: "", label: "Any subscription" }, ...(opts.data?.subscriptions ?? []).map((s) => ({ value: s.subscription_id, label: s.subscription_name }))]} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSelect control={control} name="allocation_status" label="Allocation" options={[{ value: "allocated", label: "Allocated to application" }, { value: "shared", label: "Shared services (not allocated)" }, { value: "unallocated", label: "Unallocated" }]} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSelect control={control} name="application_id" label="Application" options={[{ value: "", label: "—" }, ...(opts.data?.applications ?? []).map((a) => ({ value: String(a.id), label: a.name }))]} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSelect control={control} name="environment" label="Environment" options={[{ value: "", label: "—" }, ...(opts.data?.environments ?? []).map((e) => ({ value: e.code, label: e.name }))]} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfText control={control} name="priority" label="Priority (lower first)" type="number" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSwitch control={control} name="enabled" label="Enabled" />
        </Grid>
      </Grid>
      <RhfText control={control} name="description" label="Description" multiline />
    </FormDialog>
  );
}

function PrecedenceEditor() {
  const q = useApi<Setting[]>("/admin/settings");
  const canAdmin = useCan("admin");
  const mutate = useMutate();
  const current = (q.data?.find((s) => s.key === "attribution.precedence")?.value as string[] | undefined) ?? [];
  const [order, setOrder] = useState<string[]>([]);
  useEffect(() => setOrder(current), [JSON.stringify(current)]); // eslint-disable-line react-hooks/exhaustive-deps
  const move = (i: number, d: number) => {
    const next = [...order];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    setOrder(next);
  };
  const dirty = JSON.stringify(order) !== JSON.stringify(current);
  return (
    <Paper variant="outlined" sx={{ p: 2, height: "100%" }} data-testid="precedence-editor">
      <Typography variant="h3">Attribution precedence</Typography>
      <Typography variant="caption" component="div" sx={{ mb: 1.5 }}>
        Order in which sources are consulted for application and environment; the first source with a value wins. Subscription mapping is the recommended primary classification; untagged resources are never silently assigned to Production.
      </Typography>
      <Stack spacing={0.75}>
        {order.map((src, i) => (
          <Stack key={src} direction="row" alignItems="center" spacing={1} sx={{ p: 1, border: `1px solid ${surface.border}`, borderRadius: 1, bgcolor: "#fff" }}>
            <Typography variant="body2" sx={{ fontWeight: 700, width: 20 }}>
              {i + 1}.
            </Typography>
            <Typography variant="body2" sx={{ flex: 1 }}>
              {SOURCE_LABEL[src] ?? src}
            </Typography>
            <IconButton aria-label="Move up" disabled={!canAdmin || i === 0} onClick={() => move(i, -1)}>
              <ArrowUpwardIcon fontSize="small" />
            </IconButton>
            <IconButton aria-label="Move down" disabled={!canAdmin || i === order.length - 1} onClick={() => move(i, 1)}>
              <ArrowDownwardIcon fontSize="small" />
            </IconButton>
          </Stack>
        ))}
      </Stack>
      {canAdmin && (
        <Stack direction="row" spacing={1} sx={{ mt: 1.5 }}>
          <Button variant="contained" disabled={!dirty} onClick={() => mutate(() => api("/admin/settings/attribution.precedence", { method: "PUT", body: { value: order } }), "Precedence saved — re-apply rules to update history")} data-testid="precedence-save">
            Save order
          </Button>
          <Button disabled={!dirty} onClick={() => setOrder(current)}>
            Reset
          </Button>
        </Stack>
      )}
    </Paper>
  );
}

export function AllocationTab() {
  const tags = useApi<TagMapping[]>("/admin/tag-mappings");
  const maps = useApi<AppMapping[]>("/admin/application-mappings");
  const opts = useFilterOptions();
  const canAdmin = useCan("admin");
  const mutate = useMutate();
  const [tagEdit, setTagEdit] = useState<{ open: boolean; item: TagMapping | null }>({ open: false, item: null });
  const [mapEdit, setMapEdit] = useState<{ open: boolean; item: AppMapping | null }>({ open: false, item: null });
  const [del, setDel] = useState<{ kind: "tag" | "map"; id: number; label: string } | null>(null);
  const [reattr, setReattr] = useState(false);
  const appName = (id: number | null) => opts.data?.applications.find((a) => a.id === id)?.name ?? (id ? String(id) : "—");
  const subName = (id: string | null) => opts.data?.subscriptions.find((s) => s.subscription_id === id)?.subscription_name ?? (id ?? "Any");

  const actions = (onEdit: () => void, onDelete: () => void) =>
    canAdmin ? (
      <Stack direction="row">
        <Tooltip title="Edit">
          <IconButton aria-label="Edit" onClick={onEdit}>
            <EditOutlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Delete">
          <IconButton aria-label="Delete" onClick={onDelete}>
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    ) : null;

  const tagCols = useMemo<ColumnDef<TagMapping, unknown>[]>(
    () => [
      { accessorKey: "target_dimension", header: "Dimension", size: 140, cell: ({ getValue }) => titleCase(getValue() as string) },
      { accessorKey: "tag_key", header: "Tag key", size: 160, cell: ({ getValue }) => <Typography variant="body2" sx={{ fontFamily: "monospace" }}>{getValue() as string}</Typography> },
      { accessorKey: "tag_value", header: "Tag value", size: 140, cell: ({ getValue }) => (getValue() as string) ?? "any" },
      { accessorKey: "target_value", header: "Target value", size: 160, cell: ({ getValue }) => (getValue() as string) ?? "tag value" },
      { accessorKey: "priority", header: "Priority", size: 90, meta: { numeric: true } },
      { accessorKey: "enabled", header: "Status", size: 100, cell: ({ getValue }) => (getValue() ? <StatusChip value="ok" label="Enabled" /> : <StatusChip value="disabled" />) },
      { id: "actions", header: "", size: 90, enableSorting: false, enableHiding: false, cell: ({ row }) => actions(() => setTagEdit({ open: true, item: row.original }), () => setDel({ kind: "tag", id: row.original.id, label: `${row.original.tag_key} → ${row.original.target_dimension}` })) },
    ],
    [canAdmin], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const mapCols = useMemo<ColumnDef<AppMapping, unknown>[]>(
    () => [
      { accessorKey: "priority", header: "Priority", size: 80, meta: { numeric: true } },
      { accessorKey: "match_type", header: "Match on", size: 120, cell: ({ getValue }) => titleCase(getValue() as string) },
      { accessorKey: "pattern", header: "Pattern", size: 170, cell: ({ getValue }) => <Typography variant="body2" sx={{ fontFamily: "monospace" }}>{getValue() as string}</Typography> },
      { accessorKey: "subscription_id", header: "Subscription", size: 165, cell: ({ getValue }) => subName(getValue() as string | null) },
      { accessorKey: "allocation_status", header: "Allocation", size: 125, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
      { accessorKey: "application_id", header: "Application", size: 115, cell: ({ getValue }) => appName(getValue() as number | null) },
      { accessorKey: "environment", header: "Environment", size: 120, cell: ({ getValue }) => (getValue() ? titleCase(getValue() as string) : "—") },
      { accessorKey: "description", header: "Description", size: 190, cell: ({ getValue }) => <Typography variant="caption" noWrap component="div" title={(getValue() as string) ?? ""}>{(getValue() as string) ?? "—"}</Typography> },
      { accessorKey: "enabled", header: "Status", size: 100, cell: ({ getValue }) => (getValue() ? <StatusChip value="ok" label="Enabled" /> : <StatusChip value="disabled" />) },
      { id: "actions", header: "", size: 90, enableSorting: false, enableHiding: false, cell: ({ row }) => actions(() => setMapEdit({ open: true, item: row.original }), () => setDel({ kind: "map", id: row.original.id, label: row.original.pattern })) },
    ],
    [canAdmin, opts.data], // eslint-disable-line react-hooks/exhaustive-deps
  );

  return (
    <Stack spacing={2} data-testid="allocation-tab">
      <Alert severity="info" variant="outlined" sx={{ bgcolor: "#fff" }}>
        Every billing row is assigned to exactly one application/environment bucket, so shared infrastructure is never double counted. Rule changes apply to newly ingested data; use <b>Re-apply allocation rules</b> to update stored history (runs as a background job and rebuilds aggregates).
      </Alert>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 5 }}>
          <PrecedenceEditor />
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
            <Typography variant="h3">Re-apply allocation rules</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ my: 1 }}>
              Recomputes application, environment, allocation status, service category, owner and cost center for all stored billing records using the current subscription mappings, resource-group rules, tag mappings, category rules and precedence. Reporting aggregates are rebuilt per subscription in one transaction each.
            </Typography>
            {canAdmin && (
              <Button variant="outlined" startIcon={<ReplayIcon />} onClick={() => setReattr(true)} data-testid="reattribute">
                Re-apply allocation rules
              </Button>
            )}
          </Paper>
        </Grid>
      </Grid>
      <Section
        title="Resource-group / resource mappings"
        subtitle="Explicit overrides (e.g. a hub network resource group marked as Shared Services). Evaluated by priority; the first match wins."
        noPadding
        testId="app-mappings-section"
        actions={canAdmin ? <Button variant="contained" startIcon={<AddIcon />} onClick={() => setMapEdit({ open: true, item: null })} data-testid="app-mapping-new">New mapping</Button> : undefined}
      >
        <DataTable data={maps.data ?? []} columns={mapCols} loading={maps.isFetching} error={maps.error ? errorMessage(maps.error) : null} getRowId={(r) => String(r.id)} storageKey="admin-app-mappings" testId="app-mappings-table" emptyMessage="No resource-group mappings." />
      </Section>
      <Section
        title="Resource tag mappings"
        subtitle="Map resource tags to owner, cost center, project, team, business unit, workload — and optionally application / environment (used according to the precedence above)."
        noPadding
        testId="tag-mappings-section"
        actions={canAdmin ? <Button variant="contained" startIcon={<AddIcon />} onClick={() => setTagEdit({ open: true, item: null })} data-testid="tag-mapping-new">New tag mapping</Button> : undefined}
      >
        <DataTable data={tags.data ?? []} columns={tagCols} loading={tags.isFetching} error={tags.error ? errorMessage(tags.error) : null} getRowId={(r) => String(r.id)} storageKey="admin-tag-mappings" testId="tag-mappings-table" clientPageSize={50} />
      </Section>
      <TagForm open={tagEdit.open} item={tagEdit.item} onClose={() => setTagEdit({ open: false, item: null })} onSaved={() => { setTagEdit({ open: false, item: null }); mutate(async () => undefined, "Tag mapping saved"); }} />
      <AppMappingForm open={mapEdit.open} item={mapEdit.item} onClose={() => setMapEdit({ open: false, item: null })} onSaved={() => { setMapEdit({ open: false, item: null }); mutate(async () => undefined, "Mapping saved"); }} />
      <ConfirmDialog
        open={!!del}
        title="Delete rule"
        message={<>Delete <b>{del?.label}</b>? Stored history keeps its current allocation until rules are re-applied.</>}
        confirmLabel="Delete"
        danger
        onClose={() => setDel(null)}
        onConfirm={async () => {
          if (del) await mutate(() => api(del.kind === "tag" ? `/admin/tag-mappings/${del.id}` : `/admin/application-mappings/${del.id}`, { method: "DELETE" }), "Rule deleted");
          setDel(null);
        }}
      />
      <ConfirmDialog
        open={reattr}
        title="Re-apply allocation rules"
        message="A background job will re-attribute all stored billing records and rebuild aggregates. Reports remain available while it runs; figures update when each subscription completes."
        confirmLabel="Queue job"
        testId="reattribute-dialog"
        onClose={() => setReattr(false)}
        onConfirm={async () => {
          await mutate(() => api("/admin/reattribute", { method: "POST" }), "Re-attribution job queued", "/ingestion");
          setReattr(false);
        }}
      />
      <Box />
    </Stack>
  );
}
