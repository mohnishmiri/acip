"use client";
import SearchIcon from "@mui/icons-material/Search";
import {
  Box,
  Checkbox,
  FormControl,
  InputAdornment,
  InputLabel,
  ListItemText,
  MenuItem,
  OutlinedInput,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { DeltaText, MoneyText } from "@/components/common/Delta";
import { PageHeader } from "@/components/common/PageHeader";
import { SeverityChip, StatusChip } from "@/components/common/StatusChip";
import { ErrorState } from "@/components/common/States";
import { useGlobalFilters, useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { useUrlState } from "@/hooks/useUrlState";
import { shortDate, titleCase } from "@/lib/format";
import { useApi, useFilterOptions } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { severityColor, surface } from "@/styles/tokens";

export interface AnomalySummary {
  id: number;
  anomaly_ref: string;
  title: string;
  rule_code: string;
  detection_type: string;
  category: string;
  scope_level: string;
  detected_at: string;
  detection_date: string;
  last_detected_date: string;
  period_start: string;
  period_end: string;
  application_id: number | null;
  application: string;
  environment: string;
  environment_code: string;
  subscription_id: string;
  subscription_name: string;
  service_category: string | null;
  resource_group: string | null;
  resource_key: string | null;
  resource_name: string | null;
  previous_cost: number;
  current_cost: number;
  expected_baseline: number;
  absolute_increase: number;
  percentage_increase: number | null;
  severity: string;
  status: string;
  occurrence_count: number;
  currency: string;
  cost_type: string;
  is_demo: boolean;
}

export const ANOMALY_STATUSES = ["open", "investigating", "acknowledged", "resolved", "dismissed", "expected"];
const SEVERITIES = ["critical", "high", "medium", "low", "informational"];
const DEFAULTS = { status: "open,investigating,acknowledged", severity: "", rule: "", category: "", q: "", sort: "severity", from: "", to: "" };

function MultiSelect({ label, value, options, onChange, testId, render }: { label: string; value: string; options: { value: string; label: string }[]; onChange: (v: string) => void; testId: string; render?: (v: string) => React.ReactNode }) {
  const selected = value ? value.split(",") : [];
  return (
    <FormControl sx={{ minWidth: 170, maxWidth: 260 }}>
      <InputLabel id={`${testId}-l`}>{label}</InputLabel>
      <Select
        labelId={`${testId}-l`}
        multiple
        value={selected}
        onChange={(e) => onChange((e.target.value as string[]).join(","))}
        input={<OutlinedInput label={label} />}
        renderValue={(v) => (v.length === 0 ? "" : v.length > 2 ? `${v.length} selected` : v.map((x) => options.find((o) => o.value === x)?.label ?? x).join(", "))}
        data-testid={testId}
      >
        {options.map((o) => (
          <MenuItem key={o.value} value={o.value}>
            <Checkbox size="small" checked={selected.includes(o.value)} />
            <ListItemText primary={render ? render(o.value) : o.label} />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

export default function AnomaliesPage() {
  const router = useRouter();
  const link = useLinkWithFilters();
  const { filters } = useGlobalFilters();
  const [s, set] = useUrlState(DEFAULTS);
  const [search, setSearch] = useState(s.q);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(50);
  const opts = useFilterOptions().data;
  const rules = useApi<{ code: string; name: string }[]>("/anomalies/rules", undefined, { staleTime: 300_000 });

  useEffect(() => {
    const t = setTimeout(() => {
      if (search !== s.q) {
        set({ q: search });
        setPage(1);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [search, s.q, set]);

  const params = useMemo(
    () => ({
      status: s.status ? s.status.split(",") : undefined,
      severity: s.severity ? s.severity.split(",") : undefined,
      rule_code: s.rule ? s.rule.split(",") : undefined,
      category: s.category ? s.category.split(",") : undefined,
      application: filters.app && /^\d+$/.test(filters.app) ? [filters.app] : undefined,
      environment: filters.env ? [filters.env] : undefined,
      subscription: filters.sub ? [filters.sub] : undefined,
      date_from: s.from || undefined,
      date_to: s.to || undefined,
      search: s.q || undefined,
      sort: s.sort,
      page,
      page_size: size,
    }),
    [s, filters.app, filters.env, filters.sub, page, size],
  );
  const q = useApi<{ data: AnomalySummary[]; meta: { total: number; open_by_severity: Record<string, number> } }>("/anomalies", params);
  const counts = q.data?.meta.open_by_severity ?? {};

  const columns = useMemo<ColumnDef<AnomalySummary, unknown>[]>(
    () => [
      { accessorKey: "anomaly_ref", header: "ID", size: 110, enableSorting: false, cell: ({ getValue }) => <Typography variant="body2" sx={{ fontWeight: 600, color: "primary.main", fontVariantNumeric: "tabular-nums" }}>{getValue() as string}</Typography> },
      { accessorKey: "severity", header: "Severity", size: 120, enableSorting: false, cell: ({ getValue }) => <SeverityChip severity={getValue() as string} /> },
      { accessorKey: "title", header: "Anomaly", size: 400, enableSorting: false, enableHiding: false, cell: ({ row }) => <Box sx={{ minWidth: 0 }}><Typography variant="body2" noWrap sx={{ fontWeight: 600 }} title={row.original.title}>{row.original.title}</Typography><Typography variant="caption" noWrap component="div">{row.original.category} · {row.original.occurrence_count > 1 ? `${row.original.occurrence_count} consecutive detections` : "single detection"}</Typography></Box> },
      { accessorKey: "detection_date", header: "Detected", size: 150, enableSorting: false, cell: ({ row }) => (row.original.detection_date === row.original.last_detected_date ? shortDate(row.original.detection_date) : `${shortDate(row.original.detection_date)} – ${shortDate(row.original.last_detected_date)}`) },
      { accessorKey: "application", header: "Application", size: 130, enableSorting: false },
      { accessorKey: "environment", header: "Environment", size: 130, enableSorting: false },
      { accessorKey: "subscription_name", header: "Subscription", size: 190, enableSorting: false },
      { accessorKey: "service_category", header: "Service", size: 160, enableSorting: false, cell: ({ getValue }) => (getValue() as string) ?? "—" },
      { accessorKey: "resource_name", header: "Resource", size: 190, enableSorting: false, cell: ({ getValue }) => (getValue() as string) ?? "—" },
      { accessorKey: "expected_baseline", header: "Baseline", size: 120, enableSorting: false, meta: { numeric: true, label: "Expected baseline" }, cell: ({ row }) => <MoneyText value={row.original.expected_baseline} currency={row.original.currency} /> },
      { accessorKey: "previous_cost", header: "Previous", size: 120, enableSorting: false, meta: { numeric: true }, cell: ({ row }) => <MoneyText value={row.original.previous_cost} currency={row.original.currency} /> },
      { accessorKey: "current_cost", header: "Observed", size: 120, enableSorting: false, meta: { numeric: true, label: "Observed (current) cost" }, cell: ({ row }) => <MoneyText value={row.original.current_cost} currency={row.original.currency} bold /> },
      { accessorKey: "absolute_increase", header: "Increase", size: 120, enableSorting: false, meta: { numeric: true, label: "Absolute increase" }, cell: ({ row }) => <DeltaText value={row.original.absolute_increase} currency={row.original.currency} /> },
      { accessorKey: "percentage_increase", header: "Increase %", size: 100, enableSorting: false, meta: { numeric: true }, cell: ({ row }) => <DeltaText value={row.original.percentage_increase} kind="pct" status={row.original.percentage_increase === null ? "new" : undefined} /> },
      { accessorKey: "rule_code", header: "Rule", size: 190, enableSorting: false, cell: ({ getValue }) => titleCase((getValue() as string).toLowerCase()) },
      { accessorKey: "status", header: "Status", size: 130, enableSorting: false, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
    ],
    [],
  );

  const categories = useMemo(() => [...(opts?.service_categories ?? []), "Non-Production", "Total"].map((c) => ({ value: c, label: c })), [opts]);

  return (
    <Box data-testid="anomalies-page">
      <PageHeader title="Cost Anomalies" subtitle="Unusual expenditure detected with transparent rules combining relative (%) and absolute (currency) significance. Thresholds and sensitivity are configurable in Administration." />
      <Stack direction="row" spacing={1.5} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap data-testid="severity-strip">
        {SEVERITIES.map((sev) => {
          const active = s.severity.split(",").includes(sev);
          return (
            <Paper
              key={sev}
              variant="outlined"
              onClick={() => {
                set({ severity: active ? "" : sev });
                setPage(1);
              }}
              sx={{ px: 2, py: 1.25, minWidth: 150, cursor: "pointer", borderColor: active ? "primary.main" : surface.border, borderLeft: `4px solid ${severityColor[sev]}` }}
              data-testid={`severity-${sev}`}
            >
              <Typography variant="caption">{titleCase(sev)} · active</Typography>
              <Typography sx={{ fontSize: 20, fontWeight: 600 }}>{counts[sev] ?? 0}</Typography>
            </Paper>
          );
        })}
      </Stack>
      <Paper variant="outlined">
        <Stack direction="row" spacing={1.25} alignItems="center" flexWrap="wrap" useFlexGap sx={{ px: 1.5, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
          <TextField
            placeholder="Search title or resource"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ minWidth: 240 }}
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }, htmlInput: { "data-testid": "anomaly-search" } }}
          />
          <MultiSelect label="Status" value={s.status} options={ANOMALY_STATUSES.map((x) => ({ value: x, label: titleCase(x) }))} onChange={(v) => { set({ status: v }); setPage(1); }} testId="filter-status" />
          <MultiSelect label="Severity" value={s.severity} options={SEVERITIES.map((x) => ({ value: x, label: titleCase(x) }))} onChange={(v) => { set({ severity: v }); setPage(1); }} testId="filter-severity" render={(v) => <SeverityChip severity={v} />} />
          <MultiSelect label="Detection rule" value={s.rule} options={(rules.data ?? []).map((r) => ({ value: r.code, label: r.name }))} onChange={(v) => { set({ rule: v }); setPage(1); }} testId="filter-rule" />
          <MultiSelect label="Category" value={s.category} options={categories} onChange={(v) => { set({ category: v }); setPage(1); }} testId="filter-category" />
          <TextField type="date" label="Detected from" value={s.from} onChange={(e) => { set({ from: e.target.value }); setPage(1); }} slotProps={{ inputLabel: { shrink: true } }} sx={{ width: 150 }} />
          <TextField type="date" label="to" value={s.to} onChange={(e) => { set({ to: e.target.value }); setPage(1); }} slotProps={{ inputLabel: { shrink: true } }} sx={{ width: 150 }} />
          <FormControl sx={{ minWidth: 190 }}>
            <InputLabel id="asort">Sort by</InputLabel>
            <Select labelId="asort" label="Sort by" value={s.sort} onChange={(e) => set({ sort: e.target.value })} data-testid="anomaly-sort">
              <MenuItem value="severity">Severity</MenuItem>
              <MenuItem value="detection_date">Most recent</MenuItem>
              <MenuItem value="absolute_increase">Largest increase</MenuItem>
              <MenuItem value="percentage_increase">Highest % increase</MenuItem>
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
            getRowId={(r) => String(r.id)}
            onRowClick={(r) => router.push(link(`/anomalies/${r.id}`))}
            serverPaging={{ page, pageSize: size, total: q.data?.meta.total ?? 0, onChange: (p, sz) => { setPage(p); setSize(sz); } }}
            storageKey="anomalies"
            defaultHidden={["previous_cost", "rule_code", "subscription_name", "resource_name", "service_category", "expected_baseline"]}
            maxHeight={640}
            emptyMessage="No anomalies match the selected filters."
            toolbar={<Typography variant="body2" color="text.secondary">{q.data ? `${q.data.meta.total} anomalies · ongoing spikes are merged into one anomaly (no repeated alerts)` : "Loading…"}</Typography>}
            testId="anomalies-table"
          />
        )}
      </Paper>
    </Box>
  );
}
