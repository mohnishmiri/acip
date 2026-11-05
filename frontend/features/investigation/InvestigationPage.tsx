"use client";
/**
 * Cost Investigation — "What exactly changed?"
 * Meter-level comparison for any scope (one resource, or service / application / environment /
 * subscription via the global filters), decomposed into usage, price, meter, resource,
 * commitment and credit effects. Confirmed billing facts and unverified hypotheses are
 * presented separately.
 */
import { Autocomplete, Box, Button, FormControl, InputLabel, MenuItem, Paper, Select, Stack, TextField, Typography } from "@mui/material";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/common/PageHeader";
import { Warnings } from "@/components/common/States";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { useUrlState } from "@/hooks/useUrlState";
import { periodText } from "@/lib/format";
import type { ReportMeta } from "@/lib/types";
import { useApi, useFilterOptions } from "@/services/queries";
import { surface } from "@/styles/tokens";
import { DecompositionPanels, type Decomposition } from "../comparison/shared";

interface ResourceOption {
  id: number | null;
  key: string;
  label: string;
  resource_id: string;
  subscription_name: string | null;
  service_category: string | null;
}

const DEFAULTS = { resource: "", svc: "", cmp: "previous_equivalent" };
const MODES = [
  { value: "previous_equivalent", label: "Previous period — equivalent elapsed days" },
  { value: "previous_calendar", label: "Previous period — full calendar period" },
  { value: "same_period_last_year", label: "Same period last year" },
];

export default function InvestigationPage() {
  const link = useLinkWithFilters();
  const { apiParams, filters } = useGlobalFilters();
  const [s, set] = useUrlState(DEFAULTS);
  const opts = useFilterOptions().data;
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(term.trim()), 300);
    return () => clearTimeout(t);
  }, [term]);

  const search = useApi<{ data: ResourceOption[] }>(debounced.length >= 2 ? "/resources" : null, { ...apiParams, comparison: "none", search: debounced, sort: "current_cost", page_size: 15 });
  const selected = useApi<{ data: ResourceOption[] }>(s.resource ? "/resources" : null, { ...apiParams, comparison: "none", resource: [s.resource], page_size: 1 });
  const selectedOption = selected.data?.data[0] ?? (s.resource ? { id: null, key: s.resource.toLowerCase(), label: s.resource.split("/").pop() ?? s.resource, resource_id: s.resource, subscription_name: null, service_category: null } : null);

  const params = useMemo(
    () => ({ ...apiParams, resource: s.resource ? [s.resource] : undefined, service_category: s.svc ? [s.svc] : undefined, comparison: s.cmp }),
    [apiParams, s.resource, s.svc, s.cmp],
  );
  const q = useApi<{ data: Decomposition; meta: ReportMeta }>("/costs/meter-comparison", params);
  const meta = q.data?.meta;

  const appName = filters.app ? (opts?.applications.find((a) => String(a.id) === filters.app)?.name ?? filters.app) : "all applications";
  const envName = filters.env ? (opts?.environment_groups.find((e) => e.code === filters.env)?.name ?? filters.env) : "all environments";
  const subName = filters.sub ? (opts?.subscriptions.find((x) => x.subscription_id === filters.sub)?.subscription_name ?? filters.sub) : "all subscriptions";
  const scopeText = s.resource ? `Resource ${selectedOption?.label ?? s.resource}` : `${s.svc || "All services"} · ${appName} · ${envName} · ${subName}`;

  return (
    <Box data-testid="investigation-page">
      <PageHeader title="Cost Investigation" subtitle="What exactly changed? Compare the underlying billing meters of any resource or scope between two periods." />
      <Paper variant="outlined" sx={{ mb: 2 }} data-testid="investigation-scope">
        <Stack direction="row" spacing={1.25} alignItems="center" flexWrap="wrap" useFlexGap sx={{ px: 1.5, py: 1.25 }}>
          <Autocomplete<ResourceOption>
            sx={{ minWidth: 360, flex: 1, maxWidth: 520 }}
            options={search.data?.data ?? []}
            value={selectedOption}
            filterOptions={(x) => x}
            loading={search.isFetching}
            getOptionLabel={(o) => o.label}
            isOptionEqualToValue={(a, b) => a.key === b.key}
            onInputChange={(_, v, reason) => reason === "input" && setTerm(v)}
            onChange={(_, v) => set({ resource: v ? v.resource_id : "" })}
            noOptionsText={debounced.length < 2 ? "Type at least 2 characters" : "No matching resources"}
            renderOption={(props, o) => (
              <li {...props} key={o.key}>
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{o.label}</Typography>
                  <Typography variant="caption" noWrap component="div">{[o.service_category, o.subscription_name].filter(Boolean).join(" · ")}</Typography>
                </Box>
              </li>
            )}
            renderInput={(p) => <TextField {...p} label="Resource (optional)" placeholder="Search resource name or ID" inputProps={{ ...p.inputProps, "data-testid": "investigation-resource" }} />}
          />
          <FormControl sx={{ minWidth: 200 }} disabled={!!s.resource}>
            <InputLabel id="isvc">Azure service</InputLabel>
            <Select labelId="isvc" label="Azure service" value={s.svc} onChange={(e) => set({ svc: e.target.value })} data-testid="investigation-service">
              <MenuItem value="">All services</MenuItem>
              {(opts?.service_categories ?? []).map((c) => (
                <MenuItem key={c} value={c}>{c}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl sx={{ minWidth: 280 }}>
            <InputLabel id="icmp">Compared with</InputLabel>
            <Select labelId="icmp" label="Compared with" value={s.cmp} onChange={(e) => set({ cmp: e.target.value })} data-testid="investigation-comparison">
              {MODES.map((m) => (
                <MenuItem key={m.value} value={m.value}>{m.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
          {(s.resource || s.svc) && (
            <Button color="inherit" onClick={() => set({ resource: "", svc: "" })}>Clear scope</Button>
          )}
          {selectedOption?.id && (
            <Button component={Link} href={link(`/resources/${selectedOption.id}`)} variant="outlined" color="inherit">Resource analysis</Button>
          )}
        </Stack>
        <Box sx={{ px: 1.5, py: 1, borderTop: `1px solid ${surface.border}`, bgcolor: surface.subtle }}>
          <Typography variant="body2" data-testid="investigation-scope-text">
            <b>Scope:</b> {scopeText} · <b>Current:</b> {meta ? periodText(meta.period) : "…"} · <b>Compared with:</b> {meta?.comparison_period ? `${periodText(meta.comparison_period)} (${meta.comparison_period.label})` : "…"} · {meta?.currency ?? ""} {meta?.cost_type === "amortized" ? "amortized" : "actual"} cost
          </Typography>
          <Typography variant="caption">Application, environment, subscription, date range and cost type come from the filters in the header.</Typography>
        </Box>
      </Paper>
      <Stack spacing={2}>
        <Warnings warnings={meta?.warnings} />
        <DecompositionPanels data={q.data?.data} meta={meta} loading={q.isFetching} error={q.error} onRetry={() => q.refetch()} showResources={!s.resource} testPrefix="investigation" />
      </Stack>
    </Box>
  );
}
