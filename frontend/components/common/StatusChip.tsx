"use client";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import ReportProblemOutlinedIcon from "@mui/icons-material/ReportProblemOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import SyncIcon from "@mui/icons-material/Sync";
import { Box } from "@mui/material";
import type { ReactElement } from "react";
import { severityColor, status as S } from "@/styles/tokens";
import { titleCase } from "@/lib/format";

type Tone = "good" | "warning" | "serious" | "critical" | "info" | "neutral" | "demo";

const TONES: Record<Tone, { fg: string; bg: string; border: string }> = {
  good: { fg: "#055d05", bg: "#eef8ee", border: "#b9e2b9" },
  warning: { fg: "#7a5200", bg: "#fff7e3", border: "#f6d98d" },
  serious: { fg: "#8f3a14", bg: "#fdf0ea", border: "#f2c2ad" },
  critical: { fg: "#9b1c1c", bg: "#fdeeee", border: "#f1b8b8" },
  info: { fg: "#0c4f8c", bg: "#ebf3fc", border: "#b9d5f2" },
  neutral: { fg: "#4a4d52", bg: "#f2f3f5", border: "#dde0e4" },
  demo: { fg: "#6a3fb8", bg: "#f3effc", border: "#d6c9f2" },
};

const ICON: Record<Tone, ReactElement> = {
  good: <CheckCircleOutlineIcon sx={{ fontSize: 14 }} />,
  warning: <ReportProblemOutlinedIcon sx={{ fontSize: 14 }} />,
  serious: <ReportProblemOutlinedIcon sx={{ fontSize: 14 }} />,
  critical: <ErrorOutlineIcon sx={{ fontSize: 14 }} />,
  info: <InfoOutlinedIcon sx={{ fontSize: 14 }} />,
  neutral: <InfoOutlinedIcon sx={{ fontSize: 14 }} />,
  demo: <ScienceOutlinedIcon sx={{ fontSize: 14 }} />,
};

const STATUS_TONE: Record<string, Tone> = {
  ok: "good", fresh: "good", applied: "good", succeeded: "good", processed: "good", resolved: "good", implemented: "good", accepted: "good", delivered: "good", allocated: "good",
  degraded: "warning", delayed: "warning", partial: "warning", partially_applied: "warning", warning: "warning", awaiting_export: "warning", investigating: "info", acknowledged: "info", expected: "neutral",
  failed: "critical", error: "critical",
  processing: "info", running: "info", queued: "info", discovered: "neutral", open: "serious",
  superseded: "neutral", skipped_duplicate: "neutral", skipped_empty: "neutral", dismissed: "neutral", disabled: "neutral", untested: "neutral", skipped: "neutral", not_configured: "neutral", shared: "info", unallocated: "warning",
  demo: "demo",
  // cost movement is reported neutrally: an increase is not automatically bad (thresholds decide "notable")
  new: "info", removed: "neutral", increased: "neutral", decreased: "neutral", unchanged: "neutral", no_data: "neutral",
};

export function StatusChip({ value, label, tone }: { value: string | null | undefined; label?: string; tone?: Tone }) {
  const t: Tone = tone ?? STATUS_TONE[value ?? ""] ?? "neutral";
  const c = TONES[t];
  const icon = t === "info" && (value === "processing" || value === "running") ? <SyncIcon sx={{ fontSize: 14 }} /> : value === "queued" ? <HourglassEmptyIcon sx={{ fontSize: 14 }} /> : ICON[t];
  return (
    <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, px: 0.75, py: 0.125, borderRadius: 1, border: `1px solid ${c.border}`, bgcolor: c.bg, color: c.fg, fontSize: 11.5, fontWeight: 600, lineHeight: 1.6, whiteSpace: "nowrap" }}>
      {icon}
      {label ?? titleCase(value)}
    </Box>
  );
}

export function SeverityChip({ severity }: { severity: string }) {
  const color = severityColor[severity] ?? S.neutral;
  return (
    <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, fontSize: 12, fontWeight: 600, whiteSpace: "nowrap" }}>
      <Box component="span" sx={{ width: 10, height: 10, borderRadius: "2px", bgcolor: color, flexShrink: 0 }} aria-hidden />
      {titleCase(severity)}
    </Box>
  );
}
