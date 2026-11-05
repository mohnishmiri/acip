"use client";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import { zodResolver } from "@hookform/resolvers/zod";
import { Box, IconButton, Stack, Switch, Tooltip, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Section } from "@/components/common/Section";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { useApi } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { useMutate } from "./hooks";
import { SettingsGroup, type Setting } from "./SettingsTab";
import { errorMessage, FormDialog, KeyValueList, RhfSwitch, RhfText, useCan } from "./ui";

interface Rule {
  id: number;
  code: string;
  name: string;
  description: string | null;
  detection_type: string;
  scope_level: string;
  filters: Record<string, unknown>;
  params: Record<string, unknown>;
  enabled: boolean;
}

const jsonObject = (label: string) =>
  z.string().refine((v) => {
    try {
      const p = JSON.parse(v);
      return p !== null && typeof p === "object" && !Array.isArray(p);
    } catch {
      return false;
    }
  }, `${label} must be a JSON object`);

const schema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  description: z.string().max(2000),
  enabled: z.boolean(),
  params: jsonObject("Thresholds"),
  filters: jsonObject("Filters"),
});
type Values = z.infer<typeof schema>;

export function AnomalyRulesTab() {
  const q = useApi<Rule[]>("/anomalies/rules");
  const settings = useApi<Setting[]>("/admin/settings");
  const canManage = useCan("manage_alerts");
  const mutate = useMutate();
  const [edit, setEdit] = useState<Rule | null>(null);
  const [error, setError] = useState<string | null>(null);
  const defaults = useMemo<Values>(() => ({ name: edit?.name ?? "", description: edit?.description ?? "", enabled: edit?.enabled ?? true, params: JSON.stringify(edit?.params ?? {}, null, 2), filters: JSON.stringify(edit?.filters ?? {}, null, 2) }), [edit]);
  const { control, handleSubmit, reset, formState } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: defaults });
  useEffect(() => {
    if (edit) {
      reset(defaults);
      setError(null);
    }
  }, [edit, defaults, reset]);
  const submit = handleSubmit(async (v) => {
    if (!edit) return;
    try {
      await api(`/anomalies/rules/${edit.id}`, { method: "PUT", body: { name: v.name, description: v.description || null, enabled: v.enabled, params: JSON.parse(v.params), filters: JSON.parse(v.filters) } });
      setEdit(null);
      await mutate(async () => undefined, "Anomaly rule updated — applies from the next detection run");
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  const cols = useMemo<ColumnDef<Rule, unknown>[]>(
    () => [
      { accessorKey: "name", header: "Rule", size: 260, enableHiding: false, cell: ({ row }) => <Box><Typography variant="body2" sx={{ fontWeight: 600 }}>{row.original.name}</Typography><Typography variant="caption" sx={{ fontFamily: "monospace" }}>{row.original.code}</Typography></Box> },
      { accessorKey: "detection_type", header: "Detection", size: 150, cell: ({ getValue }) => titleCase(getValue() as string) },
      { accessorKey: "scope_level", header: "Scope", size: 170, cell: ({ getValue }) => titleCase(getValue() as string) },
      { accessorKey: "description", header: "Description", size: 380, cell: ({ getValue }) => <Typography variant="caption" noWrap component="div" title={(getValue() as string) ?? ""}>{(getValue() as string) ?? "—"}</Typography> },
      {
        accessorKey: "enabled",
        header: "Enabled",
        size: 90,
        cell: ({ row }) => (
          <Switch
            size="small"
            checked={row.original.enabled}
            disabled={!canManage}
            inputProps={{ "aria-label": `Enable ${row.original.name}` }}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => mutate(() => api(`/anomalies/rules/${row.original.id}`, { method: "PUT", body: { enabled: e.target.checked } }), e.target.checked ? "Rule enabled" : "Rule disabled")}
          />
        ),
      },
      {
        id: "actions",
        header: "",
        size: 60,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) =>
          canManage ? (
            <Tooltip title="Edit thresholds">
              <IconButton aria-label={`Edit ${row.original.name}`} onClick={(e) => { e.stopPropagation(); setEdit(row.original); }} data-testid={`anomaly-rule-edit-${row.original.code}`}>
                <EditOutlinedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          ) : null,
      },
    ],
    [canManage, mutate],
  );

  const sensitivity = (settings.data ?? []).filter((s) => s.key.startsWith("anomaly."));

  return (
    <Stack spacing={2} data-testid="anomaly-rules-tab">
      <Typography variant="body2" color="text.secondary">
        Transparent rule-based detection: each rule combines a relative threshold (% over baseline) with a minimum absolute increase so insignificant changes do not alert. Global sensitivity scales all thresholds; severity bands are evaluated on the absolute increase with a minimum percentage.
      </Typography>
      <SettingsGroup title="Sensitivity, severity bands and exclusions" settings={sensitivity} />
      <Section title="Detection rules" subtitle="Expand a rule to see its thresholds and filters" noPadding testId="anomaly-rules-section">
        <DataTable
          data={q.data ?? []}
          columns={cols}
          loading={q.isFetching}
          error={q.error ? errorMessage(q.error) : null}
          getRowId={(r) => String(r.id)}
          storageKey="admin-anomaly-rules"
          testId="anomaly-rules-table"
          renderSubRow={(r) => (
            <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                  Thresholds / parameters
                </Typography>
                <KeyValueList data={r.params} />
              </Box>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                  Scope filters
                </Typography>
                <KeyValueList data={r.filters} />
              </Box>
            </Stack>
          )}
        />
      </Section>
      <FormDialog open={!!edit} title={`Edit rule — ${edit?.code ?? ""}`} onClose={() => setEdit(null)} onSubmit={submit} busy={formState.isSubmitting} error={error} maxWidth="md" testId="anomaly-rule-dialog">
        <RhfText control={control} name="name" label="Name" required />
        <RhfText control={control} name="description" label="Description" multiline />
        <RhfText control={control} name="params" label="Thresholds / parameters (JSON)" multiline helperText="e.g. pct_threshold, min_abs, method, window, min_history_days, category_overrides" testId="anomaly-rule-params" />
        <RhfText control={control} name="filters" label="Scope filters (JSON)" multiline helperText='e.g. {"environment_groups": ["non_production"], "service_categories": ["Networking"]}' />
        <RhfSwitch control={control} name="enabled" label="Enabled" />
      </FormDialog>
    </Stack>
  );
}
