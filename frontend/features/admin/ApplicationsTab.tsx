"use client";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button, IconButton, Tooltip, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Section } from "@/components/common/Section";
import { StatusChip } from "@/components/common/StatusChip";
import { api } from "@/lib/api";
import { useApi } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { useMutate } from "./hooks";
import { ConfirmDialog, errorMessage, FormDialog, RhfSwitch, RhfText, useCan } from "./ui";

interface App {
  id: number;
  code: string;
  name: string;
  description: string | null;
  owner: string | null;
  is_active: boolean;
  sort_order: number;
  is_demo: boolean;
  subscription_count: number;
}

const schema = z.object({
  code: z.string().trim().regex(/^[a-z0-9][a-z0-9_-]{0,63}$/, "Lower-case letters, digits, - and _ (max 64)"),
  name: z.string().trim().min(1, "Name is required").max(200),
  description: z.string().max(2000),
  owner: z.string().max(200),
  is_active: z.boolean(),
  sort_order: z.number({ error: "Enter a number" }).int().min(0).max(10000),
});
type Values = z.infer<typeof schema>;

export function ApplicationsTab() {
  const q = useApi<App[]>("/admin/applications");
  const canAdmin = useCan("admin");
  const mutate = useMutate();
  const [editing, setEditing] = useState<App | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<App | null>(null);
  const defaults = useMemo<Values>(() => ({ code: editing?.code ?? "", name: editing?.name ?? "", description: editing?.description ?? "", owner: editing?.owner ?? "", is_active: editing?.is_active ?? true, sort_order: editing?.sort_order ?? 100 }), [editing]);
  const { control, handleSubmit, reset, formState } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: defaults });
  useEffect(() => {
    if (open) {
      reset(defaults);
      setError(null);
    }
  }, [open, defaults, reset]);

  const submit = handleSubmit(async (v) => {
    setError(null);
    const body = { ...v, description: v.description || null, owner: v.owner || null };
    try {
      if (editing) await api(`/admin/applications/${editing.id}`, { method: "PUT", body });
      else await api("/admin/applications", { method: "POST", body });
      setOpen(false);
      await mutate(async () => undefined, editing ? "Application updated" : "Application created", "/applications");
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  const columns = useMemo<ColumnDef<App, unknown>[]>(
    () => [
      { accessorKey: "name", header: "Application", size: 220, cell: ({ row }) => <Typography variant="body2" sx={{ fontWeight: 600 }}>{row.original.name}{row.original.is_demo ? " (demo)" : ""}</Typography> },
      { accessorKey: "code", header: "Code", size: 120 },
      { accessorKey: "description", header: "Description", size: 300, cell: ({ getValue }) => (getValue() as string) ?? "—" },
      { accessorKey: "owner", header: "Owner", size: 200, cell: ({ getValue }) => (getValue() as string) ?? "—" },
      { accessorKey: "subscription_count", header: "Subscriptions", size: 120, meta: { numeric: true } },
      { accessorKey: "sort_order", header: "Order", size: 80, meta: { numeric: true } },
      { accessorKey: "is_active", header: "Status", size: 100, cell: ({ getValue }) => (getValue() ? <StatusChip value="ok" label="Active" /> : <StatusChip value="disabled" label="Inactive" />) },
      {
        id: "actions",
        header: "",
        size: 90,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) =>
          canAdmin ? (
            <>
              <Tooltip title="Edit">
                <IconButton aria-label={`Edit ${row.original.name}`} onClick={() => { setEditing(row.original); setOpen(true); }}>
                  <EditOutlinedIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title={row.original.subscription_count ? "Reassign its subscriptions before deleting" : "Delete"}>
                <span>
                  <IconButton aria-label={`Delete ${row.original.name}`} disabled={row.original.subscription_count > 0} onClick={() => setDeleting(row.original)} data-testid={`application-delete-${row.original.id}`}>
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            </>
          ) : null,
      },
    ],
    [canAdmin],
  );

  return (
    <Section
      title="Applications"
      subtitle="Business applications. Subscriptions map to an application and environment (primary classification); new applications need no code change."
      noPadding
      testId="applications-admin-section"
      actions={canAdmin ? <Button variant="contained" startIcon={<AddIcon />} onClick={() => { setEditing(null); setOpen(true); }} data-testid="application-new">New application</Button> : undefined}
    >
      <DataTable data={q.data ?? []} columns={columns} loading={q.isFetching} error={q.error ? errorMessage(q.error) : null} getRowId={(r) => String(r.id)} storageKey="admin-applications" testId="applications-admin-table" />
      <FormDialog open={open} title={editing ? `Edit application — ${editing.name}` : "New application"} onClose={() => setOpen(false)} onSubmit={submit} busy={formState.isSubmitting} error={error} testId="application-dialog">
        <RhfText control={control} name="code" label="Code" required disabled={!!editing} helperText="Stable identifier used in configuration and tags" testId="application-code" />
        <RhfText control={control} name="name" label="Display name" required testId="application-name" />
        <RhfText control={control} name="description" label="Description" multiline />
        <RhfText control={control} name="owner" label="Owner" />
        <RhfText control={control} name="sort_order" label="Sort order" type="number" />
        <RhfSwitch control={control} name="is_active" label="Active" />
      </FormDialog>
      <ConfirmDialog
        open={!!deleting}
        title={`Delete application — ${deleting?.name ?? ""}`}
        message="The application is removed only if no subscription, budget or billing history references it; otherwise set it inactive."
        confirmLabel="Delete"
        danger
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          const a = deleting;
          setDeleting(null);
          if (a) await mutate(() => api(`/admin/applications/${a.id}`, { method: "DELETE" }), "Application deleted", "/admin/applications", "/applications");
        }}
        testId="application-delete-dialog"
      />
    </Section>
  );
}
