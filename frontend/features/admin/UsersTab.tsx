"use client";
import AddIcon from "@mui/icons-material/Add";
import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Box, Button, Chip, Stack, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Section } from "@/components/common/Section";
import { api } from "@/lib/api";
import { dateTime, titleCase } from "@/lib/format";
import { useApi, useFilterOptions, useMe } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { useMutate } from "./hooks";
import { errorMessage, FormDialog, RhfSelect, RhfText, useCan } from "./ui";

interface Role {
  code: string;
  name: string;
  description: string;
  entra_app_role: string | null;
  permissions: string[];
}
interface User {
  id: number;
  external_id: string;
  email: string | null;
  display_name: string | null;
  is_active: boolean;
  last_login_at: string | null;
  assignments: { id: number; role: string; application_id: number | null }[];
}

const schema = z.object({
  external_id: z.string().trim().min(1, "Entra object id is required").max(200),
  email: z.string().trim().refine((v) => v === "" || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v), "Enter a valid email"),
  display_name: z.string().max(200),
  role: z.enum(["administrator", "finops_analyst", "engineering_lead", "viewer"]),
  application_id: z.string(),
});
type Values = z.infer<typeof schema>;

export function UsersTab() {
  const roles = useApi<Role[]>("/admin/roles");
  const canAdmin = useCan("admin");
  const users = useApi<User[]>(canAdmin ? "/admin/users" : null);
  const opts = useFilterOptions();
  const { data: me } = useMe();
  const mutate = useMutate();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { control, handleSubmit, reset, formState } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { external_id: "", email: "", display_name: "", role: "viewer", application_id: "" } });
  useEffect(() => {
    if (open) {
      reset({ external_id: "", email: "", display_name: "", role: "viewer", application_id: "" });
      setError(null);
    }
  }, [open, reset]);
  const appName = (id: number | null) => (id === null ? "all applications" : (opts.data?.applications.find((a) => a.id === id)?.name ?? `application ${id}`));

  const submit = handleSubmit(async (v) => {
    try {
      await api("/admin/role-assignments", { method: "POST", body: { ...v, email: v.email || null, display_name: v.display_name || null, application_id: v.application_id ? Number(v.application_id) : null } });
      setOpen(false);
      await mutate(async () => undefined, "Role assigned");
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  const roleCols = useMemo<ColumnDef<Role, unknown>[]>(
    () => [
      { accessorKey: "name", header: "Role", size: 170, cell: ({ getValue }) => <Typography variant="body2" sx={{ fontWeight: 600 }}>{getValue() as string}</Typography> },
      { accessorKey: "entra_app_role", header: "Entra app role value", size: 190, cell: ({ getValue }) => <Typography variant="body2" sx={{ fontFamily: "monospace" }}>{(getValue() as string) ?? "—"}</Typography> },
      { accessorKey: "description", header: "Description", size: 380 },
      { id: "perms", header: "Permissions", size: 420, accessorFn: (r) => r.permissions.join(" "), cell: ({ row }) => <Stack direction="row" spacing={0.5} sx={{ overflow: "hidden" }}>{row.original.permissions.map((p) => <Chip key={p} label={titleCase(p)} variant="outlined" />)}</Stack> },
    ],
    [],
  );
  const userCols = useMemo<ColumnDef<User, unknown>[]>(
    () => [
      { accessorKey: "display_name", header: "User", size: 240, cell: ({ row }) => <Box><Typography variant="body2" sx={{ fontWeight: 600 }}>{row.original.display_name ?? row.original.email ?? row.original.external_id}</Typography><Typography variant="caption">{row.original.email ?? row.original.external_id}</Typography></Box> },
      {
        id: "assignments",
        header: "Role assignments",
        size: 460,
        accessorFn: (r) => r.assignments.length,
        cell: ({ row }) => (
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {row.original.assignments.length === 0 && <Typography variant="caption">Token app roles only</Typography>}
            {row.original.assignments.map((a) => (
              <Chip
                key={a.id}
                label={`${titleCase(a.role)} · ${appName(a.application_id)}`}
                onDelete={canAdmin ? () => mutate(() => api(`/admin/role-assignments/${a.id}`, { method: "DELETE" }), "Assignment removed") : undefined}
              />
            ))}
          </Stack>
        ),
      },
      { accessorKey: "last_login_at", header: "Last sign-in", size: 180, cell: ({ getValue }) => dateTime(getValue() as string | null) },
      { accessorKey: "is_active", header: "Active", size: 80, cell: ({ getValue }) => (getValue() ? "Yes" : "No") },
    ],
    [canAdmin, opts.data], // eslint-disable-line react-hooks/exhaustive-deps
  );

  return (
    <Stack spacing={2} data-testid="users-tab">
      <Alert severity="info" variant="outlined" sx={{ bgcolor: "#fff" }}>
        Application users sign in with Microsoft Entra ID; roles come from the API app registration&apos;s <b>app roles</b> (token claim) and/or the assignments below. An assignment scoped to an application restricts that user to the application&apos;s subscriptions. This identity is separate from the cost-collection service principal.
        {me?.auth_mode === "disabled" && " Authentication is currently disabled (local development) — every request runs as a local administrator."}
      </Alert>
      <Section title="Roles" noPadding testId="roles-section">
        <DataTable data={roles.data ?? []} columns={roleCols} loading={roles.isFetching} getRowId={(r) => r.code} storageKey="admin-roles" testId="roles-table" />
      </Section>
      {canAdmin && (
        <Section title="Users & assignments" subtitle="Users appear after their first sign-in or when an assignment is created for their Entra object id." noPadding testId="users-section" actions={<Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpen(true)} data-testid="role-assign-new">Assign role</Button>}>
          <DataTable data={users.data ?? []} columns={userCols} loading={users.isFetching} error={users.error ? errorMessage(users.error) : null} getRowId={(r) => String(r.id)} storageKey="admin-users" emptyMessage="No users yet." testId="users-table" />
        </Section>
      )}
      <FormDialog open={open} title="Assign role" onClose={() => setOpen(false)} onSubmit={submit} busy={formState.isSubmitting} error={error} testId="role-assign-dialog">
        <RhfText control={control} name="external_id" label="Entra object id (oid)" required testId="role-assign-oid" />
        <RhfText control={control} name="email" label="Email (optional)" />
        <RhfText control={control} name="display_name" label="Display name (optional)" />
        <RhfSelect control={control} name="role" label="Role" options={(roles.data ?? []).map((r) => ({ value: r.code, label: r.name }))} />
        <RhfSelect control={control} name="application_id" label="Scope" options={[{ value: "", label: "All applications" }, ...(opts.data?.applications ?? []).map((a) => ({ value: String(a.id), label: `Only ${a.name}` }))]} />
      </FormDialog>
    </Stack>
  );
}
