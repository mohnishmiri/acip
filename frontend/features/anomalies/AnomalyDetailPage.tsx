"use client";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import {
  Alert,
  Box,
  Button,
  FormControl,
  Grid,
  InputLabel,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import { useMemo, useState } from "react";
import EChart from "@/charts/EChart";
import { DeltaText, MoneyText } from "@/components/common/Delta";
import { PageHeader } from "@/components/common/PageHeader";
import { Section } from "@/components/common/Section";
import { SeverityChip, StatusChip } from "@/components/common/StatusChip";
import { ChartSkeleton, ErrorState } from "@/components/common/States";
import { useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { bucketLabel, dateTime, money, num, pct, periodText, titleCase } from "@/lib/format";
import { useApi, useApiMutation, useMe } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { surface } from "@/styles/tokens";
import { costSeriesOption, Stat, StatStrip } from "../comparison/shared";
import { ANOMALY_STATUSES, type AnomalySummary } from "./AnomaliesPage";

interface TopMeter {
  meter_category: string | null;
  meter_name: string | null;
  unit: string | null;
  observed_cost: number;
  baseline_cost: number;
  diff: number;
  observed_quantity: number | null;
  baseline_quantity: number | null;
  quantity_diff: number | null;
}
interface TopResource {
  resource_key: string;
  resource_name: string;
  resource_id: number | null;
  observed_cost: number;
  baseline_cost: number;
  diff: number;
}
interface AnomalyDetail extends AnomalySummary {
  evidence: {
    baseline_method: string;
    baseline_description: string;
    baseline_points: { period: string; cost: number }[];
    observed: number;
    baseline: number;
    observed_period: { start: string; end: string };
    rule: { code: string; name: string; detection_type: string; params: Record<string, unknown>; sensitivity: string };
    top_meters: TopMeter[];
    top_resources: TopResource[];
    history: { date: string; cost: number }[];
    extra: Record<string, unknown>;
    thresholds_applied?: Record<string, unknown>;
  };
  explanation: string;
  recommended_steps: string[];
  resource_id: number | null;
  resource_arm_id: string | null;
  events: { id: number; event_type: string; from_status: string | null; to_status: string | null; comment: string | null; actor: string; details: Record<string, unknown> | null; created_at: string }[];
  explanation_note: string;
}

export default function AnomalyDetailPage({ id }: { id: string }) {
  const link = useLinkWithFilters();
  const q = useApi<{ data: AnomalyDetail }>(`/anomalies/${id}`);
  const me = useMe().data;
  const canEdit = !!me?.permissions.includes("manage_anomalies");
  const a = q.data?.data;
  const [status, setStatus] = useState<string>("");
  const [comment, setComment] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const setStatusM = useApiMutation<{ status: string; comment?: string }>(`/anomalies/${id}/status`, "POST", ["/anomalies"]);
  const commentM = useApiMutation<{ comment: string }>(`/anomalies/${id}/comments`, "POST", ["/anomalies"]);
  const currency = a?.currency ?? "USD";

  const chart = useMemo(() => {
    if (!a) return null;
    const h = a.evidence.history;
    const pts = h.map((p) => ({ label: bucketLabel(p.date, "daily"), value: p.cost }));
    const op = a.evidence.observed_period;
    const days = Math.round((Date.parse(op.end) - Date.parse(op.start)) / 86_400_000) + 1;
    const s = h.findIndex((p) => p.date === op.start);
    const e = h.findIndex((p) => p.date === op.end);
    const baselineDaily = a.evidence.baseline > 0 ? a.evidence.baseline / (a.detection_type === "daily_spike" ? 1 : a.detection_type === "weekly_spike" || a.detection_type === "continuous_increase" ? 7 : days) : null;
    return costSeriesOption(pts, currency, {
      kind: "bar",
      markLine: baselineDaily,
      markLineLabel: a.detection_type === "daily_spike" ? "Expected baseline" : "Baseline (daily avg)",
      highlight: s >= 0 ? [s, e >= 0 ? e : h.length - 1] : null,
      name: "Daily cost",
    });
  }, [a, currency]);

  const meterCols = useMemo<ColumnDef<TopMeter, unknown>[]>(
    () => [
      { id: "meter", header: "Meter", size: 260, accessorFn: (r) => r.meter_name, cell: ({ row }) => <Box><Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{row.original.meter_name ?? "(no meter)"}</Typography><Typography variant="caption" noWrap component="div">{row.original.meter_category}</Typography></Box> },
      { accessorKey: "baseline_quantity", header: "Baseline qty", size: 120, meta: { numeric: true }, cell: ({ getValue }) => num(getValue() as number | null, 2) },
      { accessorKey: "observed_quantity", header: "Observed qty", size: 120, meta: { numeric: true }, cell: ({ getValue }) => num(getValue() as number | null, 2) },
      { accessorKey: "quantity_diff", header: "Qty change", size: 110, meta: { numeric: true }, cell: ({ getValue }) => num(getValue() as number | null, 2) },
      { accessorKey: "unit", header: "Unit", size: 100 },
      { accessorKey: "baseline_cost", header: "Baseline cost", size: 120, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      { accessorKey: "observed_cost", header: "Observed cost", size: 120, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} bold /> },
      { accessorKey: "diff", header: "Difference", size: 120, meta: { numeric: true }, cell: ({ getValue }) => <DeltaText value={getValue() as number} currency={currency} /> },
    ],
    [currency],
  );
  const resCols = useMemo<ColumnDef<TopResource, unknown>[]>(
    () => [
      { accessorKey: "resource_name", header: "Resource", size: 280, cell: ({ row }) => (row.original.resource_id ? <Link href={link(`/resources/${row.original.resource_id}`)} style={{ color: "#0f6cbd", fontWeight: 600, textDecoration: "none" }}>{row.original.resource_name}</Link> : row.original.resource_name) },
      { accessorKey: "baseline_cost", header: "Baseline cost", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
      { accessorKey: "observed_cost", header: "Observed cost", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} bold /> },
      { accessorKey: "diff", header: "Difference", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <DeltaText value={getValue() as number} currency={currency} /> },
    ],
    [currency, link],
  );
  const baselineCols = useMemo<ColumnDef<{ period: string; cost: number }, unknown>[]>(
    () => [
      { accessorKey: "period", header: "Baseline period", size: 220, cell: ({ getValue }) => { const v = getValue() as string; return v.includes("/") ? periodText({ start: v.split("/")[0], end: v.split("/")[1] }) : periodText({ start: v, end: v }); } },
      { accessorKey: "cost", header: "Cost", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> },
    ],
    [currency],
  );

  if (q.error) return <Paper variant="outlined"><ErrorState error={q.error} onRetry={() => q.refetch()} /></Paper>;
  if (!a) return <Paper variant="outlined" sx={{ p: 2 }}><ChartSkeleton height={300} /></Paper>;

  const scope = [a.application !== "—" ? a.application : null, a.environment !== "—" ? a.environment : null, a.subscription_name !== "—" ? a.subscription_name : null, a.service_category, a.resource_group, a.resource_name].filter(Boolean).join(" · ");
  const ev = a.evidence;
  const thresholds = ev.thresholds_applied ?? {};
  const investigateHref = a.resource_arm_id ? link("/investigation", { resource: a.resource_arm_id, preset: "custom", start: a.period_start, end: a.period_end, cmp: "previous_equivalent" }) : null;

  return (
    <Box data-testid="anomaly-detail">
      <Button component={Link} href={link("/anomalies")} size="small" startIcon={<ArrowBackIcon fontSize="small" />} sx={{ mb: 1 }}>
        All anomalies
      </Button>
      <PageHeader
        title={a.title}
        subtitle={
          <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap component="span">
            <Typography component="span" variant="body2" sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }} data-testid="anomaly-ref">{a.anomaly_ref}</Typography>
            <SeverityChip severity={a.severity} />
            <StatusChip value={a.status} />
            <span>{scope}</span>
          </Stack>
        }
        actions={
          <>
            {a.resource_id && <Button component={Link} href={link(`/resources/${a.resource_id}`)} variant="outlined" color="inherit">Resource analysis</Button>}
            {investigateHref && <Button component={Link} href={investigateHref} variant="contained" data-testid="investigate-link">Investigate what changed</Button>}
          </>
        }
      />
      <Stack spacing={2}>
        {a.is_demo && <Alert severity="info" variant="outlined" sx={{ bgcolor: "#fff" }}>Detected on DEMO DATA (synthetic).</Alert>}
        <StatStrip testId="anomaly-figures">
          <Stat label="Observed period" value={periodText(ev.observed_period)} sub={`Detected ${dateTime(a.detected_at)}`} />
          <Stat label="Observed cost" value={money(a.current_cost, currency)} testId="anomaly-observed" />
          <Stat label="Expected baseline" value={money(a.expected_baseline, currency)} sub={ev.baseline_description} testId="anomaly-baseline" />
          <Stat label="Previous comparable" value={money(a.previous_cost, currency)} />
          <Stat label="Absolute increase" value={<DeltaText value={a.absolute_increase} currency={currency} />} testId="anomaly-increase" />
          <Stat label="Increase %" value={a.percentage_increase === null ? "New spend" : pct(a.percentage_increase)} />
          <Stat label="Detection rule" value={<Typography sx={{ fontSize: 13.5, fontWeight: 600 }}>{ev.rule.name}</Typography>} sub={`Sensitivity: ${ev.rule.sensitivity}${a.occurrence_count > 1 ? ` · ${a.occurrence_count} detections` : ""}`} />
        </StatStrip>

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 8 }}>
            <Section
              title="Historical trend"
              subtitle="Daily cost of the anomaly scope over the last 6 weeks; shaded = observed period, line = expected baseline"
              testId="anomaly-trend"
              table={<DataTable data={ev.history} columns={[{ accessorKey: "date", header: "Date", size: 140 }, { accessorKey: "cost", header: "Cost", size: 140, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={currency} /> }] as ColumnDef<{ date: string; cost: number }, unknown>[]} storageKey="anomaly-history" maxHeight={330} />}
            >
              {chart ? <EChart option={chart} height={300} ariaLabel="Anomaly historical daily cost" testId="echart-anomaly-trend" /> : <ChartSkeleton />}
            </Section>
          </Grid>
          <Grid size={{ xs: 12, lg: 4 }}>
            <Paper variant="outlined" sx={{ height: "100%" }} data-testid="anomaly-evidence">
              <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
                <Typography variant="h3">Supporting evidence</Typography>
                <Typography variant="caption">Baseline: {ev.baseline_description}</Typography>
              </Box>
              <DataTable data={ev.baseline_points} columns={baselineCols} storageKey="anomaly-baseline" maxHeight={200} emptyMessage="No baseline (new spend)." />
              <Box sx={{ px: 2, py: 1.25, borderTop: `1px solid ${surface.border}` }}>
                <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Thresholds applied</Typography>
                <Stack spacing={0.25}>
                  {Object.entries(thresholds).filter(([, v]) => typeof v !== "object").map(([k, v]) => (
                    <Typography key={k} variant="caption" component="div">
                      {titleCase(k)}: <b>{String(v)}</b>
                    </Typography>
                  ))}
                </Stack>
              </Box>
            </Paper>
          </Grid>
        </Grid>

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 6 }}>
            <Paper variant="outlined" sx={{ height: "100%", borderLeft: "3px solid #0ca30c" }} data-testid="measured-facts">
              <Stack direction="row" spacing={1} alignItems="center" sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
                <FactCheckOutlinedIcon sx={{ fontSize: 18, color: "#006300" }} />
                <Box>
                  <Typography variant="h3">Measured facts</Typography>
                  <Typography variant="caption">{a.explanation_note}</Typography>
                </Box>
              </Stack>
              <Typography variant="body2" sx={{ p: 2, lineHeight: 1.6 }} data-testid="anomaly-explanation">
                {a.explanation}
              </Typography>
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, lg: 6 }}>
            <Paper variant="outlined" sx={{ height: "100%", borderLeft: "3px solid #c9ced6", bgcolor: surface.subtle }} data-testid="suggested-steps">
              <Stack direction="row" spacing={1} alignItems="center" sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
                <HelpOutlineIcon sx={{ fontSize: 18, color: "text.secondary" }} />
                <Box>
                  <Typography variant="h3">Suggested steps — not confirmed causes</Typography>
                  <Typography variant="caption">Investigation guidance for this service category; verify before drawing conclusions.</Typography>
                </Box>
              </Stack>
              <List dense>
                {a.recommended_steps.map((st, i) => (
                  <ListItem key={i} alignItems="flex-start">
                    <ListItemIcon sx={{ minWidth: 26, mt: 0.6 }}>
                      <Typography variant="caption" sx={{ fontWeight: 700 }}>{i + 1}.</Typography>
                    </ListItemIcon>
                    <ListItemText primary={st} slotProps={{ primary: { sx: { fontSize: 12.75 } } }} />
                  </ListItem>
                ))}
              </List>
            </Paper>
          </Grid>
        </Grid>

        <Paper variant="outlined" data-testid="anomaly-meters">
          <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
            <Typography variant="h3">Meter-level breakdown &amp; usage quantity change</Typography>
            <Typography variant="caption">Observed period vs baseline average, by billing meter.</Typography>
          </Box>
          <DataTable data={ev.top_meters} columns={meterCols} storageKey="anomaly-meters" emptyMessage="No meter-level change recorded." />
        </Paper>

        {ev.top_resources.length > 0 && (
          <Paper variant="outlined" data-testid="anomaly-resources">
            <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
              <Typography variant="h3">Contributing resources</Typography>
            </Box>
            <DataTable data={ev.top_resources} columns={resCols} storageKey="anomaly-resources" getRowId={(r) => r.resource_key || "__none__"} />
          </Paper>
        )}

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 5 }}>
            <Paper variant="outlined" sx={{ p: 2 }} data-testid="anomaly-status-panel">
              <Typography variant="h3" sx={{ mb: 1.5 }}>Investigation status</Typography>
              {!canEdit && <Alert severity="info" sx={{ mb: 1.5 }}>Your role ({me?.primary_role?.replace(/_/g, " ") ?? "viewer"}) can view but not change the investigation status.</Alert>}
              <Stack spacing={1.5}>
                <FormControl fullWidth disabled={!canEdit}>
                  <InputLabel id="st">Status</InputLabel>
                  <Select labelId="st" label="Status" value={status || a.status} onChange={(e) => setStatus(e.target.value)} data-testid="anomaly-status-select">
                    {ANOMALY_STATUSES.map((x) => (
                      <MenuItem key={x} value={x}>{titleCase(x)}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <TextField label="Comment / investigation note" multiline minRows={3} value={comment} onChange={(e) => setComment(e.target.value)} disabled={!canEdit} slotProps={{ htmlInput: { maxLength: 4000, "data-testid": "anomaly-comment" } }} />
                <Stack direction="row" spacing={1}>
                  <Button
                    variant="contained"
                    disabled={!canEdit || setStatusM.isPending || (status || a.status) === a.status}
                    onClick={async () => {
                      try {
                        await setStatusM.mutateAsync({ status: status || a.status, comment: comment || undefined });
                        setComment("");
                        setStatus("");
                        setMsg("Status updated");
                        q.refetch();
                      } catch (e) {
                        setMsg(e instanceof Error ? e.message : "Update failed");
                      }
                    }}
                    data-testid="anomaly-status-save"
                  >
                    Update status
                  </Button>
                  <Button
                    variant="outlined"
                    color="inherit"
                    disabled={!canEdit || !comment.trim() || commentM.isPending}
                    onClick={async () => {
                      try {
                        await commentM.mutateAsync({ comment: comment.trim() });
                        setComment("");
                        setMsg("Note added");
                        q.refetch();
                      } catch (e) {
                        setMsg(e instanceof Error ? e.message : "Could not add note");
                      }
                    }}
                    data-testid="anomaly-comment-save"
                  >
                    Add note only
                  </Button>
                </Stack>
              </Stack>
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, lg: 7 }}>
            <Paper variant="outlined" data-testid="anomaly-timeline">
              <Box sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
                <Typography variant="h3">Activity</Typography>
              </Box>
              <List dense sx={{ maxHeight: 340, overflowY: "auto" }}>
                {a.events.map((e) => (
                  <ListItem key={e.id} alignItems="flex-start" divider>
                    <ListItemIcon sx={{ minWidth: 30, mt: 0.5 }}>
                      {e.event_type === "comment" ? <ChatBubbleOutlineIcon sx={{ fontSize: 16 }} /> : e.event_type === "status_change" ? <SwapHorizIcon sx={{ fontSize: 18 }} /> : <FiberManualRecordIcon sx={{ fontSize: 10, color: "text.disabled", mt: 0.5 }} />}
                    </ListItemIcon>
                    <ListItemText
                      primary={
                        e.event_type === "status_change" ? (
                          <span>Status changed {e.from_status ? <>from <b>{titleCase(e.from_status)}</b> </> : null}to <b>{titleCase(e.to_status)}</b></span>
                        ) : e.event_type === "comment" ? (
                          <span>{e.comment}</span>
                        ) : e.event_type === "redetected" ? (
                          <span>Re-detected on {String(e.details?.date ?? "")} (observed {money(Number(e.details?.observed ?? 0), currency)} vs baseline {money(Number(e.details?.baseline ?? 0), currency)})</span>
                        ) : (
                          <span>Detected by rule {String(e.details?.rule ?? a.rule_code)}</span>
                        )
                      }
                      secondary={`${e.actor} · ${dateTime(e.created_at)}${e.event_type === "status_change" && e.comment ? ` · “${e.comment}”` : ""}`}
                      slotProps={{ primary: { sx: { fontSize: 12.75 } }, secondary: { sx: { fontSize: 11.5 } } }}
                    />
                  </ListItem>
                ))}
              </List>
            </Paper>
          </Grid>
        </Grid>
      </Stack>
      <Snackbar open={!!msg} autoHideDuration={4000} onClose={() => setMsg(null)} message={msg} />
    </Box>
  );
}
