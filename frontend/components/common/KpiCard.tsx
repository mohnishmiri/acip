"use client";
import { Box, Paper, Tooltip, Typography } from "@mui/material";
import Link from "next/link";
import EChart from "@/charts/EChart";
import { sparklineOption } from "@/charts/options";
import { compactMoney, money, pct, periodText } from "@/lib/format";
import type { Kpi } from "@/lib/types";
import { status, surface } from "@/styles/tokens";
import { useMemo } from "react";

const SIG: Record<string, { color: string; label: string }> = {
  notable_increase: { color: "#b42318", label: "Notable increase" },
  notable_decrease: { color: status.goodText, label: "Notable decrease" },
  normal: { color: "#6b6f76", label: "Within normal variation" },
};

export function KpiCard({ kpi, currency, href, spark }: { kpi: Kpi; currency: string; href?: string; spark?: number[] }) {
  const sig = kpi.significance ? SIG[kpi.significance] : null;
  const isPct = kpi.display === "pct";
  const option = useMemo(() => (spark && spark.length > 1 ? sparklineOption(spark) : null), [spark]);
  const arrow = kpi.pct === null || kpi.pct === undefined ? "" : kpi.pct > 0 ? "▲ " : kpi.pct < 0 ? "▼ " : "";
  const body = (
    <Paper
      variant="outlined"
      data-testid={`kpi-${kpi.key}`}
      sx={{ p: 1.5, height: "100%", display: "flex", flexDirection: "column", gap: 0.5, transition: "border-color .15s", "&:hover": href ? { borderColor: "primary.main" } : undefined, cursor: href ? "pointer" : "default" }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        <Typography variant="subtitle2" noWrap sx={{ flex: 1 }}>
          {kpi.title}
        </Typography>
        {kpi.kind !== "actual" && (
          <Typography variant="overline" sx={{ color: kpi.kind === "forecast" ? "#a3480f" : "text.secondary", lineHeight: 1 }}>
            {kpi.kind === "forecast" ? "Projection" : kpi.kind === "estimate" ? "Estimate" : "Budget"}
          </Typography>
        )}
      </Box>
      <Box sx={{ display: "flex", alignItems: "flex-end", gap: 1 }}>
        <Typography sx={{ fontSize: 21, fontWeight: 600, lineHeight: 1.2, letterSpacing: -0.2 }} data-testid={`kpi-${kpi.key}-value`}>
          {isPct ? pct(kpi.pct) : kpi.current === null ? "—" : compactMoney(kpi.current, currency)}
        </Typography>
        {option && (
          <Box sx={{ flex: 1, minWidth: 50, height: 26, mb: 0.25 }}>
            <EChart option={option} height={26} ariaLabel={`${kpi.title} trend`} />
          </Box>
        )}
      </Box>
      {kpi.previous !== null && kpi.kind === "actual" ? (
        <Typography variant="caption" component="div" noWrap>
          {isPct ? `${compactMoney(kpi.current, currency)} vs ${compactMoney(kpi.previous, currency)}` : `vs ${compactMoney(kpi.previous, currency)}`}
          {kpi.comparison_period ? ` · ${periodText(kpi.comparison_period)}` : ""}
        </Typography>
      ) : (
        <Typography variant="caption" component="div" noWrap>
          {kpi.note ?? " "}
        </Typography>
      )}
      {kpi.kind === "actual" && kpi.pct !== undefined && (
        <Tooltip title={sig ? `${sig.label} (thresholds configurable in Settings)` : ""}>
          <Typography variant="caption" sx={{ fontWeight: 600, color: sig?.color ?? "text.secondary" }} noWrap>
            {kpi.pct === null ? "No comparable data" : `${arrow}${pct(kpi.pct)} · ${money(kpi.diff, currency, { sign: true, decimals: 0 })}`}
          </Typography>
        </Tooltip>
      )}
      {kpi.kind !== "actual" && kpi.pct !== null && kpi.key !== "savings" && (
        <Typography variant="caption" sx={{ fontWeight: 600, color: kpi.significance === "notable_increase" ? "#b42318" : "text.secondary" }} noWrap>
          {kpi.key === "budget" ? `${pct(kpi.pct, { sign: false })} consumed` : kpi.key === "budget_variance" ? `${pct(kpi.pct)} of budget` : `${arrow}${pct(kpi.pct)} vs previous month`}
        </Typography>
      )}
      <Box sx={{ borderTop: `1px dashed ${surface.border}`, display: "none" }} />
    </Paper>
  );
  return href ? (
    <Link href={href} style={{ textDecoration: "none", color: "inherit", display: "block", height: "100%" }}>
      {body}
    </Link>
  ) : (
    body
  );
}
