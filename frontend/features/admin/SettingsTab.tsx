"use client";
import { Box, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { z } from "zod";
import { api } from "@/lib/api";
import { useApi } from "@/services/queries";
import { surface } from "@/styles/tokens";
import { useMutate } from "./hooks";
import { errorMessage, useCan } from "./ui";

export interface Setting {
  key: string;
  value: unknown;
  default: unknown;
  description: string;
}

const ENUMS: Record<string, { value: string | number; label: string }[]> = {
  "reporting.week_start_isodow": [1, 2, 3, 4, 5, 6, 7].map((d) => ({ value: d, label: ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][d] })),
  "reporting.default_cost_type": [{ value: "actual", label: "Actual cost" }, { value: "amortized", label: "Amortized cost" }],
  "anomaly.sensitivity": [{ value: "low", label: "Low (fewer alerts)" }, { value: "medium", label: "Medium" }, { value: "high", label: "High (more alerts)" }],
  "forecast.default_method": [{ value: "run_rate", label: "Average daily run-rate" }, { value: "recent", label: "Recent daily spending (7 days)" }, { value: "trend", label: "Historical linear trend (60 days)" }],
};

/** zod validator for a setting's edited value, derived from its default's type. */
function validatorFor(s: Setting) {
  if (s.key === "reporting.default_currency") return z.string().regex(/^[A-Z]{3}$/, "3-letter upper-case currency code");
  if (s.key === "reporting.week_start_isodow") return z.number().int().min(1).max(7);
  if (typeof s.default === "number") return z.number({ error: "Enter a number" }).min(0, "Must be zero or positive");
  if (typeof s.default === "string") return z.string().min(1, "Required");
  if (Array.isArray(s.default)) return z.array(z.unknown());
  return z.unknown();
}

export function SettingRow({ s }: { s: Setting }) {
  const canAdmin = useCan("admin");
  const mutate = useMutate();
  const isJson = typeof s.default === "object";
  const initial = isJson ? JSON.stringify(s.value, null, 2) : String(s.value ?? "");
  const [draft, setDraft] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setDraft(initial), [initial]);
  const dirty = draft !== initial;

  const parse = (): { ok: true; value: unknown } | { ok: false; error: string } => {
    let raw: unknown = draft;
    if (isJson) {
      try {
        raw = JSON.parse(draft);
      } catch {
        return { ok: false, error: "Invalid JSON" };
      }
    } else if (typeof s.default === "number") raw = draft === "" ? NaN : Number(draft);
    const r = validatorFor(s).safeParse(raw);
    return r.success ? { ok: true, value: r.data } : { ok: false, error: r.error.issues[0]?.message ?? "Invalid value" };
  };

  const save = async () => {
    const p = parse();
    if (!p.ok) {
      setError(p.error);
      return;
    }
    setError(null);
    await mutate(() => api(`/admin/settings/${s.key}`, { method: "PUT", body: { value: p.value } }), `Saved ${s.key}`, "/dashboard", "/costs", "/budgets");
  };

  const options = ENUMS[s.key];
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(240px, 1fr) minmax(260px, 1.2fr) auto" }, gap: 1.5, alignItems: "start", py: 1.25, borderBottom: `1px solid ${surface.border}` }} data-testid={`setting-${s.key}`}>
      <Box>
        <Typography variant="body2" sx={{ fontWeight: 600, fontFamily: "monospace" }}>
          {s.key}
        </Typography>
        <Typography variant="caption" component="div">
          {s.description}
        </Typography>
        <Typography variant="caption" component="div">
          Default: <code>{JSON.stringify(s.default)}</code>
        </Typography>
      </Box>
      {options ? (
        <TextField select value={draft} onChange={(e) => setDraft(String(e.target.value))} disabled={!canAdmin} error={!!error} helperText={error ?? " "} fullWidth>
          {options.map((o) => (
            <MenuItem key={o.value} value={String(o.value)}>
              {o.label}
            </MenuItem>
          ))}
        </TextField>
      ) : (
        <TextField
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={!canAdmin}
          multiline={isJson}
          minRows={isJson ? 3 : undefined}
          maxRows={isJson ? 12 : undefined}
          type={!isJson && typeof s.default === "number" ? "number" : "text"}
          error={!!error}
          helperText={error ?? " "}
          fullWidth
          slotProps={{ htmlInput: { style: isJson ? { fontFamily: "monospace", fontSize: 12 } : undefined, "aria-label": s.key } }}
        />
      )}
      <Stack direction="row" spacing={1} sx={{ pt: 0.5 }}>
        <Button variant="contained" size="small" disabled={!canAdmin || !dirty} onClick={save}>
          Save
        </Button>
        <Button size="small" disabled={!dirty} onClick={() => { setDraft(initial); setError(null); }}>
          Reset
        </Button>
      </Stack>
    </Box>
  );
}

export function SettingsGroup({ title, settings }: { title: string; settings: Setting[] }) {
  if (!settings.length) return null;
  return (
    <Paper variant="outlined" sx={{ px: 2, py: 1 }}>
      <Typography variant="h3" sx={{ py: 1 }}>
        {title}
      </Typography>
      {settings.map((s) => (
        <SettingRow key={s.key} s={s} />
      ))}
    </Paper>
  );
}

const GROUPS: { prefix: string; title: string }[] = [
  { prefix: "reporting.", title: "Reporting" },
  { prefix: "freshness.", title: "Data freshness" },
  { prefix: "attribution.", title: "Allocation" },
  { prefix: "anomaly.", title: "Anomaly detection" },
  { prefix: "forecast.", title: "Forecasting" },
  { prefix: "savings.", title: "Potential savings" },
  { prefix: "ingestion.", title: "Ingestion" },
  { prefix: "retention.", title: "Retention" },
];

export function SettingsTab() {
  const q = useApi<Setting[]>("/admin/settings");
  const groups = useMemo(() => GROUPS.map((g) => ({ ...g, items: (q.data ?? []).filter((s) => s.key.startsWith(g.prefix)) })), [q.data]);
  if (q.error) return <Typography color="error">{errorMessage(q.error)}</Typography>;
  return (
    <Stack spacing={2} data-testid="settings-tab">
      <Typography variant="body2" color="text.secondary">
        Business rules that administrators can change at runtime. Infrastructure configuration (database, identities, storage) comes from environment variables and is not editable here.
      </Typography>
      {groups.map((g) => (
        <SettingsGroup key={g.prefix} title={g.title} settings={g.items} />
      ))}
    </Stack>
  );
}
