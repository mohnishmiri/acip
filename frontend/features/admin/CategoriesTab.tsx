"use client";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Grid, IconButton, Stack, Tooltip, Typography } from "@mui/material";
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
import { useMutate } from "./hooks";
import { ConfirmDialog, errorMessage, FormDialog, RhfSelect, RhfSwitch, RhfText, useCan } from "./ui";

interface Rule {
  id: number;
  match_field: string;
  pattern: string;
  category: string;
  priority: number;
  enabled: boolean;
  description: string | null;
}
const FIELDS = ["resource_group", "resource_type", "meter_category", "meter_subcategory", "meter_name", "service_name", "consumed_service"] as const;

const schema = z.object({
  match_field: z.enum(FIELDS),
  pattern: z.string().trim().min(1, "Pattern is required").max(300),
  category: z.string().trim().min(1, "Category is required").max(100),
  priority: z.number({ error: "Enter a number" }).int().min(0).max(10000),
  enabled: z.boolean(),
  description: z.string().max(2000),
});
type Values = z.infer<typeof schema>;

export function CategoriesTab() {
  const q = useApi<Rule[]>("/admin/category-rules");
  const opts = useFilterOptions();
  const canAdmin = useCan("admin");
  const mutate = useMutate();
  const [edit, setEdit] = useState<{ open: boolean; item: Rule | null }>({ open: false, item: null });
  const [del, setDel] = useState<Rule | null>(null);
  const [error, setError] = useState<string | null>(null);
  const defaults = useMemo<Values>(() => ({ match_field: (edit.item?.match_field as Values["match_field"]) ?? "meter_category", pattern: edit.item?.pattern ?? "", category: edit.item?.category ?? "", priority: edit.item?.priority ?? 100, enabled: edit.item?.enabled ?? true, description: edit.item?.description ?? "" }), [edit.item]);
  const { control, handleSubmit, reset, formState } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: defaults });
  useEffect(() => {
    if (edit.open) {
      reset(defaults);
      setError(null);
    }
  }, [edit.open, defaults, reset]);
  const submit = handleSubmit(async (v) => {
    const body = { ...v, description: v.description || null };
    try {
      if (edit.item) await api(`/admin/category-rules/${edit.item.id}`, { method: "PUT", body });
      else await api("/admin/category-rules", { method: "POST", body });
      setEdit({ open: false, item: null });
      await mutate(async () => undefined, "Category rule saved");
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  const categories = useMemo(() => Array.from(new Set([...(opts.data?.service_categories ?? []), ...(q.data ?? []).map((r) => r.category)])).sort(), [opts.data, q.data]);

  const cols = useMemo<ColumnDef<Rule, unknown>[]>(
    () => [
      { accessorKey: "priority", header: "Priority", size: 90, meta: { numeric: true } },
      { accessorKey: "match_field", header: "Match field", size: 160, cell: ({ getValue }) => titleCase(getValue() as string) },
      { accessorKey: "pattern", header: "Pattern", size: 260, cell: ({ getValue }) => <Typography variant="body2" sx={{ fontFamily: "monospace" }}>{getValue() as string}</Typography> },
      { accessorKey: "category", header: "Reporting category", size: 220, cell: ({ getValue }) => <Typography variant="body2" sx={{ fontWeight: 600 }}>{getValue() as string}</Typography> },
      { accessorKey: "description", header: "Description", size: 200, cell: ({ getValue }) => (getValue() as string) ?? "—" },
      { accessorKey: "enabled", header: "Status", size: 100, cell: ({ getValue }) => (getValue() ? <StatusChip value="ok" label="Enabled" /> : <StatusChip value="disabled" />) },
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
                <IconButton aria-label="Edit" onClick={() => setEdit({ open: true, item: row.original })}>
                  <EditOutlinedIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Delete">
                <IconButton aria-label="Delete" onClick={() => setDel(row.original)}>
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          ) : null,
      },
    ],
    [canAdmin],
  );

  return (
    <Stack spacing={2} data-testid="categories-tab">
      <Alert severity="info" variant="outlined" sx={{ bgcolor: "#fff" }}>
        Billing rows are classified into reporting service categories by the first matching rule (lowest priority number first). For example, resources in AKS node resource groups (<code>mc_*</code>) report as Azure Kubernetes Service even though they are billed as Virtual Machines, Storage or Load Balancer. Rows with no match report as &quot;Other Services&quot;.
      </Alert>
      <Section
        title="Service category rules"
        noPadding
        testId="category-rules-section"
        actions={canAdmin ? <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEdit({ open: true, item: null })} data-testid="category-rule-new">New rule</Button> : undefined}
      >
        <DataTable data={q.data ?? []} columns={cols} loading={q.isFetching} error={q.error ? errorMessage(q.error) : null} getRowId={(r) => String(r.id)} storageKey="admin-category-rules" defaultHidden={["description"]} clientPageSize={50} testId="category-rules-table" />
      </Section>
      <FormDialog open={edit.open} title={edit.item ? "Edit category rule" : "New category rule"} onClose={() => setEdit({ open: false, item: null })} onSubmit={submit} busy={formState.isSubmitting} error={error} testId="category-rule-dialog">
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <RhfSelect control={control} name="match_field" label="Match field" options={FIELDS.map((f) => ({ value: f, label: titleCase(f) }))} />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <RhfText control={control} name="priority" label="Priority (lower first)" type="number" />
          </Grid>
        </Grid>
        <RhfText control={control} name="pattern" label="Pattern (case-insensitive glob)" required helperText="e.g. log analytics, microsoft.sql/*, mc_*" testId="category-rule-pattern" />
        <RhfText control={control} name="category" label="Reporting category" required helperText={`Existing: ${categories.slice(0, 12).join(", ")}`} testId="category-rule-category" />
        <RhfText control={control} name="description" label="Description" />
        <RhfSwitch control={control} name="enabled" label="Enabled" />
      </FormDialog>
      <ConfirmDialog
        open={!!del}
        title="Delete category rule"
        message={<>Delete the rule <b>{del?.match_field} = {del?.pattern}</b> → {del?.category}?</>}
        confirmLabel="Delete"
        danger
        onClose={() => setDel(null)}
        onConfirm={async () => {
          if (del) await mutate(() => api(`/admin/category-rules/${del.id}`, { method: "DELETE" }), "Rule deleted");
          setDel(null);
        }}
      />
    </Stack>
  );
}
