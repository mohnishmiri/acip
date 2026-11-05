"use client";
import SearchIcon from "@mui/icons-material/Search";
import { Autocomplete, Box, FormControl, InputAdornment, InputLabel, MenuItem, Paper, Select, Stack, TextField, Typography } from "@mui/material";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { DeltaText, MoneyText } from "@/components/common/Delta";
import { ExportMenu } from "@/components/common/ExportMenu";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusChip } from "@/components/common/StatusChip";
import { ErrorState, Warnings } from "@/components/common/States";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { useUrlState } from "@/hooks/useUrlState";
import { money, num, periodText } from "@/lib/format";
import type { ReportMeta, Totals } from "@/lib/types";
import { useApi, useFilterOptions } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { surface } from "@/styles/tokens";
import { Stat, StatStrip } from "../comparison/shared";

export interface ResourceRow {
  id: number | null;
  key: string;
  label: string;
  resource_id: string;
  resource_name: string;
  current: number;
  previous?: number;
  diff?: number;
  pct?: number | null;
  status?: string;
  share_of_total?: number | null;
  subscription_id: string | null;
  subscription_name: string | null;
  application: string | null;
  environment: string | null;
  resource_group: string | null;
  resource_type: string | null;
  service_category: string | null;
  region: string | null;
  owner: string | null;
  cost_center: string | null;
  sku: string | null;
  tags: Record<string, string> | null;
  first_seen_date: string | null;
  billing_currency: string;
  primary_meter: { meter_category: string | null; meter_name: string | null; unit: string | null; quantity: number | null; meter_count: number } | null;
}

const DEFAULTS = { q: "", svc: "", rg: "", region: "", rtype: "", owner: "", cc: "", tag: "", sort: "abs_diff", dir: "desc" };

/** Table column id -> backend sort key (direction handled with sort_dir). */
const SORT_MAP: Record<string, string> = { label: "name", current: "current_cost", previous: "previous_cost", diff: "largest_increase", pct: "pct_increase" };
const SORT_LABELS: Record<string, string> = {
  abs_diff: "Largest absolute change",
  current_cost: "Current cost",
  previous_cost: "Previous cost",
  largest_increase: "Largest increase",
  largest_decrease: "Largest decrease",
  pct_increase: "Highest % increase",
  name: "Name",
};

function FilterSelect({ label, value, options, onChange, testId }: { label: string; value: string; options: string[]; onChange: (v: string) => void; testId: string }) {
  return (
    <Autocomplete
      size="small"
      options={options}
      value={value || null}
      onChange={(_, v) => onChange(v ?? "")}
      sx={{ minWidth: 180, maxWidth: 240, bgcolor: "#fff" }}
      renderInput={(p) => <TextField {...p} label={label} />}
      data-testid={testId}
      autoHighlight
    />
  );
}

export default function ResourcesPage() {
  const router = useRouter();
  const link = useLinkWithFilters();
  const { apiParams } = useGlobalFilters();
  const [s, set] = useUrlState(DEFAULTS);
  const [search, setSearch] = useState(s.q);
  const [tagInput, setTagInput] = useState(s.tag);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(50);
  const opts = useFilterOptions().data;

  useEffect(() => {
    const t = setTimeout(() => {
      if (search !== s.q) {
        set({ q: search });
        setPage(1);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [search, s.q, set]);

  const filterParams = useMemo(
    () => ({
      ...apiParams,
      search: s.q || undefined,
      service_category: s.svc ? [s.svc] : undefined,
      resource_group: s.rg ? [s.rg] : undefined,
      region: s.region ? [s.region] : undefined,
      resource_type: s.rtype ? [s.rtype] : undefined,
      owner: s.owner ? [s.owner] : undefined,
      cost_center: s.cc ? [s.cc] : undefined,
      tag: s.tag && s.tag.includes("=") ? [s.tag] : undefined,
    }),
    [apiParams, s],
  );
  const params = useMemo(() => ({ ...filterParams, sort: s.sort, sort_dir: s.dir, page, page_size: size }), [filterParams, s.sort, s.dir, page, size]);
  const q = useApi<{ data: ResourceRow[]; meta: ReportMeta & { totals: Totals } }>("/resources", params);
  const meta = q.data?.meta;
  const currency = meta?.currency ?? "USD";
  const hasCmp = !!meta?.comparison_period;

  const sorting: SortingState = useMemo(() => {
    const col = Object.entries(SORT_MAP).find(([, v]) => v === s.sort)?.[0];
    return col ? [{ id: col, desc: s.dir === "desc" }] : [];
  }, [s.sort, s.dir]);

  const columns = useMemo<ColumnDef<ResourceRow, unknown>[]>(
    () => [
      { id: "label", accessorKey: "label", header: "Resource name", size: 250, enableHiding: false, cell: ({ row }) => <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}><Typography variant="body2" noWrap sx={{ fontWeight: 600, color: "primary.main", minWidth: 0 }} title={row.original.resource_id}>{row.original.label}</Typography>{row.original.status === "new" && <StatusChip value="new" label="New" />}</Stack> },
      { accessorKey: "resource_id", header: "Resource ID", size: 320, enableSorting: false, cell: ({ getValue }) => <Typography variant="caption" noWrap title={getValue() as string} sx={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{getValue() as string}</Typography> },
      { accessorKey: "application", header: "Application", size: 115, enableSorting: false },
      { accessorKey: "environment", header: "Environment", size: 125, enableSorting: false },
      { accessorKey: "subscription_name", header: "Subscription", size: 190, enableSorting: false },
      { accessorKey: "resource_group", header: "Resource group", size: 200, enableSorting: false },
      { accessorKey: "service_category", header: "Service", size: 160, enableSorting: false },
      { accessorKey: "resource_type", header: "Resource type", size: 230, enableSorting: false },
      { accessorKey: "region", header: "Region", size: 110, enableSorting: false },
      { accessorKey: "owner", header: "Owner", size: 200, enableSorting: false, cell: ({ getValue }) => (getValue() as string) ?? <Typography variant="caption">Untagged</Typography> },
      { accessorKey: "cost_center", header: "Cost center", size: 110, enableSorting: false },
      ...(hasCmp ? [{ id: "previous", accessorKey: "previous", header: "Previous", size: 120, meta: { numeric: true }, cell: ({ getValue }: { getValue: () => unknown }) => <MoneyText value={getValue() as number} currency={currency} /> } as ColumnDef<ResourceRow, unknown>] : []),
      { id: "current", accessorKey: "current", header: "Current", size: 120, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} bold /> },
      ...(hasCmp
        ? ([
            { id: "diff", accessorKey: "diff", header: "Difference", size: 120, meta: { numeric: true }, cell: ({ row }) => <DeltaText value={row.original.diff} currency={currency} /> },
            { id: "pct", accessorKey: "pct", header: "Change %", size: 100, meta: { numeric: true }, cell: ({ row }) => <DeltaText value={row.original.pct} kind="pct" status={row.original.status} /> },
          ] as ColumnDef<ResourceRow, unknown>[])
        : []),
      { id: "quantity", header: "Usage quantity", size: 130, enableSorting: false, meta: { numeric: true, label: "Usage quantity (primary meter)" }, accessorFn: (r) => r.primary_meter?.quantity, cell: ({ row }) => (row.original.primary_meter ? `${num(row.original.primary_meter.quantity, 2)}` : "—") },
      { id: "unit", header: "Unit", size: 100, enableSorting: false, accessorFn: (r) => r.primary_meter?.unit },
      { id: "meter_name", header: "Meter", size: 180, enableSorting: false, meta: { label: "Primary meter name" }, accessorFn: (r) => r.primary_meter?.meter_name, cell: ({ row }) => (row.original.primary_meter ? `${row.original.primary_meter.meter_name}${row.original.primary_meter.meter_count > 1 ? ` (+${row.original.primary_meter.meter_count - 1})` : ""}` : "—") },
      { id: "meter_category", header: "Meter category", size: 150, enableSorting: false, accessorFn: (r) => r.primary_meter?.meter_category },
      { accessorKey: "sku", header: "SKU", size: 150, enableSorting: false },
      { accessorKey: "billing_currency", header: "Currency", size: 90, enableSorting: false },
      { id: "tags", header: "Tags", size: 280, enableSorting: false, accessorFn: (r) => Object.entries(r.tags ?? {}).map(([k, v]) => `${k}=${v}`).join("; "), cell: ({ getValue }) => <Typography variant="caption" noWrap title={getValue() as string}>{(getValue() as string) || "—"}</Typography> },
    ],
    [currency, hasCmp],
  );

  return (
    <Box data-testid="resources-page">
      <PageHeader
        title="Resource Analysis"
        subtitle="Investigate individual Azure resources: cost, change, usage and billing meters. Sorting, search and paging run on the server."
        actions={<ExportMenu params={{ ...filterParams, sort: s.sort, sort_dir: s.dir }} view="resources" />}
      />
      <Stack spacing={1.5}>
        <Warnings warnings={meta?.warnings} />
        <StatStrip testId="resources-summary">
          <Stat label={`Current · ${meta ? periodText(meta.period) : "…"}`} value={meta?.totals ? money(meta.totals.current, currency) : "…"} />
          <Stat label={hasCmp ? `Previous · ${periodText(meta?.comparison_period)}` : "Comparison"} value={hasCmp && meta?.totals ? money(meta.totals.previous, currency) : "None"} />
          <Stat label="Difference" value={hasCmp && meta?.totals ? <DeltaText value={meta.totals.diff} currency={currency} /> : "—"} />
          <Stat label="Resources" value={meta ? (meta.total ?? 0).toLocaleString() : "…"} sub="matching the filters" testId="resources-count" />
        </StatStrip>
        <Paper variant="outlined">
          <Stack direction="row" spacing={1.25} alignItems="center" flexWrap="wrap" useFlexGap sx={{ px: 1.5, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
            <TextField
              placeholder="Search name or resource ID"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              sx={{ minWidth: 260 }}
              slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }, htmlInput: { "data-testid": "resource-search" } }}
            />
            <FilterSelect label="Service" value={s.svc} options={opts?.service_categories ?? []} onChange={(v) => { set({ svc: v }); setPage(1); }} testId="filter-service" />
            <FilterSelect label="Resource group" value={s.rg} options={opts?.resource_groups ?? []} onChange={(v) => { set({ rg: v }); setPage(1); }} testId="filter-rg" />
            <FilterSelect label="Region" value={s.region} options={opts?.regions ?? []} onChange={(v) => { set({ region: v }); setPage(1); }} testId="filter-region" />
            <FilterSelect label="Resource type" value={s.rtype} options={opts?.resource_types ?? []} onChange={(v) => { set({ rtype: v }); setPage(1); }} testId="filter-type" />
            <FilterSelect label="Owner" value={s.owner} options={opts?.owners ?? []} onChange={(v) => { set({ owner: v }); setPage(1); }} testId="filter-owner" />
            <FilterSelect label="Cost center" value={s.cc} options={opts?.cost_centers ?? []} onChange={(v) => { set({ cc: v }); setPage(1); }} testId="filter-cc" />
            <TextField
              label="Tag (key=value)"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onBlur={() => { set({ tag: tagInput }); setPage(1); }}
              onKeyDown={(e) => { if (e.key === "Enter") { set({ tag: tagInput }); setPage(1); } }}
              error={!!tagInput && !tagInput.includes("=")}
              sx={{ width: 190 }}
              slotProps={{ htmlInput: { "data-testid": "filter-tag" } }}
            />
            <FormControl sx={{ minWidth: 210 }}>
              <InputLabel id="rsort">Sort by</InputLabel>
              <Select labelId="rsort" label="Sort by" value={s.sort} onChange={(e) => set({ sort: e.target.value, dir: e.target.value === "name" ? "asc" : "desc" })} data-testid="resource-sort">
                {Object.entries(SORT_LABELS).map(([v, l]) => (
                  <MenuItem key={v} value={v}>{l}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
          {q.error ? (
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          ) : (
            <DataTable
              data={q.data?.data ?? []}
              columns={columns}
              loading={q.isFetching}
              getRowId={(r) => r.key || "__none__"}
              onRowClick={(r) => r.id && router.push(link(`/resources/${r.id}`))}
              serverSorting={{
                sorting,
                onChange: (next) => {
                  const first = next[0];
                  if (!first) set({ sort: "abs_diff", dir: "desc" });
                  else set({ sort: SORT_MAP[first.id] ?? "abs_diff", dir: first.desc ? "desc" : "asc" });
                  setPage(1);
                },
              }}
              serverPaging={{ page, pageSize: size, total: meta?.total ?? 0, onChange: (p, sz) => { setPage(p); setSize(sz); } }}
              storageKey="resources-v2"
              defaultHidden={["resource_id", "subscription_name", "resource_group", "resource_type", "region", "owner", "cost_center", "meter_name", "meter_category", "sku", "billing_currency", "tags"]}
              maxHeight={640}
              emptyMessage="No resources match the selected filters."
              toolbar={<Typography variant="body2" color="text.secondary">{meta ? `${(meta.total ?? 0).toLocaleString()} resources · sorted by ${SORT_LABELS[s.sort]?.toLowerCase()} (${s.dir === "asc" ? "ascending" : "descending"}) · click a row for details` : "Loading…"}</Typography>}
              testId="resources-table"
            />
          )}
        </Paper>
      </Stack>
    </Box>
  );
}
