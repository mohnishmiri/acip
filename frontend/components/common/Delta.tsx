"use client";
import { Box, Typography } from "@mui/material";
import { money, pct } from "@/lib/format";

const UP = "#b42318";
const DOWN = "#006300";

/** Signed change; the +/- sign carries direction, so it is never conveyed by colour alone. */
export function DeltaText({ value, currency, kind = "money", status, muted }: { value: number | null | undefined; currency?: string; kind?: "money" | "pct"; status?: string | null; muted?: boolean }) {
  if (value === null || value === undefined) {
    if (status === "new") return <Typography component="span" variant="body2" sx={{ fontWeight: 600, color: UP }}>New</Typography>;
    return <Typography component="span" variant="body2" color="text.secondary">—</Typography>;
  }
  const up = value > 0;
  const zero = value === 0;
  const color = muted || zero ? "text.secondary" : up ? UP : DOWN;
  return (
    <Box component="span" sx={{ display: "inline-flex", alignItems: "center", color, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
      {kind === "pct" ? pct(value) : money(value, currency ?? "USD", { sign: true })}
    </Box>
  );
}

export function MoneyText({ value, currency, bold }: { value: number | null | undefined; currency?: string; bold?: boolean }) {
  return (
    <Typography component="span" variant="body2" sx={{ fontWeight: bold ? 600 : 400, fontVariantNumeric: "tabular-nums", color: value !== null && value !== undefined && value < 0 ? "#b42318" : "inherit" }}>
      {money(value, currency ?? "USD")}
    </Typography>
  );
}
