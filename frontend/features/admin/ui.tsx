"use client";
/**
 * Small UI helpers shared by the allocation / planning / operations pages:
 * dialogs, React Hook Form field wrappers, key/value evidence rendering, permission hook,
 * utilisation meter and a toast.
 */
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormHelperText,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Snackbar,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { createContext, type ReactNode, useCallback, useContext, useState } from "react";
import { type Control, Controller, type FieldPath, type FieldValues } from "react-hook-form";
import { compactMoney, money, pct, titleCase } from "@/lib/format";
import { useMe } from "@/services/queries";
import { surface } from "@/styles/tokens";

export function useCan(permission: string): boolean {
  const { data } = useMe();
  return !!data?.permissions.includes(permission);
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Request failed";
}

// --------------------------------------------------------------------------- toast ---
const ToastCtx = createContext<(msg: string, severity?: "success" | "error" | "info") => void>(() => undefined);
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ msg: string; severity: "success" | "error" | "info" } | null>(null);
  const show = useCallback((msg: string, severity: "success" | "error" | "info" = "success") => setState({ msg, severity }), []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      <Snackbar open={!!state} autoHideDuration={5000} onClose={() => setState(null)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }}>
        {state ? (
          <Alert severity={state.severity} variant="filled" onClose={() => setState(null)} sx={{ fontSize: 12.5 }}>
            {state.msg}
          </Alert>
        ) : undefined}
      </Snackbar>
    </ToastCtx.Provider>
  );
}

// ------------------------------------------------------------------------- dialogs ---
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  danger,
  busy,
  onConfirm,
  onClose,
  testId,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
  testId?: string;
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth data-testid={testId}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" component="div">
          {message}
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="inherit">
          Cancel
        </Button>
        <Button onClick={onConfirm} variant="contained" color={danger ? "error" : "primary"} disabled={busy} data-testid={testId ? `${testId}-confirm` : undefined}>
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function FormDialog({
  open,
  title,
  onClose,
  onSubmit,
  submitLabel = "Save",
  busy,
  error,
  children,
  maxWidth = "sm",
  testId,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  onSubmit: () => void;
  submitLabel?: string;
  busy?: boolean;
  error?: string | null;
  children: ReactNode;
  maxWidth?: "xs" | "sm" | "md" | "lg";
  testId?: string;
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth={maxWidth} fullWidth data-testid={testId}>
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <DialogTitle>{title}</DialogTitle>
        <DialogContent dividers sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 2 }}>
          {error && <Alert severity="error">{error}</Alert>}
          {children}
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} color="inherit">
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={busy} data-testid={testId ? `${testId}-submit` : undefined}>
            {submitLabel}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

// ------------------------------------------------------------- RHF field wrappers ---
export function RhfText<T extends FieldValues>({
  control,
  name,
  label,
  type,
  helperText,
  multiline,
  required,
  disabled,
  placeholder,
  testId,
}: {
  control: Control<T>;
  name: FieldPath<T>;
  label: string;
  type?: string;
  helperText?: string;
  multiline?: boolean;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  testId?: string;
}) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <TextField
          {...field}
          value={field.value ?? ""}
          onChange={(e) => field.onChange(type === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value)}
          label={label}
          type={type}
          required={required}
          disabled={disabled}
          placeholder={placeholder}
          multiline={multiline}
          minRows={multiline ? 3 : undefined}
          error={!!fieldState.error}
          helperText={fieldState.error?.message ?? helperText}
          slotProps={{ inputLabel: type === "date" ? { shrink: true } : undefined, htmlInput: { "data-testid": testId } }}
          fullWidth
        />
      )}
    />
  );
}

export function RhfSelect<T extends FieldValues>({
  control,
  name,
  label,
  options,
  helperText,
  disabled,
  multiple,
  testId,
}: {
  control: Control<T>;
  name: FieldPath<T>;
  label: string;
  options: { value: string; label: string }[];
  helperText?: string;
  disabled?: boolean;
  multiple?: boolean;
  testId?: string;
}) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <FormControl fullWidth error={!!fieldState.error} disabled={disabled}>
          <InputLabel id={`${name}-label`}>{label}</InputLabel>
          <Select
            labelId={`${name}-label`}
            label={label}
            multiple={multiple}
            value={field.value ?? (multiple ? [] : "")}
            onChange={(e) => field.onChange(e.target.value)}
            onBlur={field.onBlur}
            data-testid={testId}
            renderValue={multiple ? (v) => (v as string[]).map((x) => options.find((o) => o.value === x)?.label ?? x).join(", ") : undefined}
          >
            {options.map((o) => (
              <MenuItem key={o.value} value={o.value}>
                {o.label}
              </MenuItem>
            ))}
          </Select>
          <FormHelperText>{fieldState.error?.message ?? helperText}</FormHelperText>
        </FormControl>
      )}
    />
  );
}

export function RhfSwitch<T extends FieldValues>({ control, name, label }: { control: Control<T>; name: FieldPath<T>; label: string }) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => <FormControlLabel control={<Switch checked={!!field.value} onChange={(e) => field.onChange(e.target.checked)} />} label={<Typography variant="body2">{label}</Typography>} />}
    />
  );
}

// ------------------------------------------------------------------ evidence lists ---
function renderValue(v: unknown): ReactNode {
  if (v === null || v === undefined || v === "") return <span style={{ color: "#6b6f76" }}>—</span>;
  if (Array.isArray(v)) return v.length ? v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ") : "—";
  if (typeof v === "object") return <KeyValueList data={v as Record<string, unknown>} nested />;
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return String(v);
}

export function KeyValueList({ data, nested }: { data: Record<string, unknown>; nested?: boolean }) {
  const entries = Object.entries(data ?? {});
  if (!entries.length) return <Typography variant="caption">No evidence recorded.</Typography>;
  return (
    <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: "minmax(140px, max-content) 1fr", columnGap: 2, rowGap: 0.5, fontSize: 12.5, pl: nested ? 1 : 0, borderLeft: nested ? `2px solid ${surface.border}` : "none" }}>
      {entries.map(([k, v]) => (
        <Box key={k} sx={{ display: "contents" }}>
          <Box component="dt" sx={{ color: "text.secondary", fontWeight: 600 }}>
            {titleCase(k)}
          </Box>
          <Box component="dd" sx={{ m: 0, wordBreak: "break-word" }}>
            {renderValue(v)}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

// -------------------------------------------------------------------------- meter ---
/** Budget utilisation: fill = consumption, marker = forecast; colour steps by severity. */
export function UtilizationMeter({ utilization, forecastPct, label, testId }: { utilization: number | null; forecastPct?: number | null; label: string; testId?: string }) {
  const u = utilization ?? 0;
  const fu = forecastPct ?? null;
  const color = u >= 100 ? "#d03b3b" : u >= 90 ? "#ec835a" : u >= 80 ? "#fab219" : "#2a78d6";
  return (
    <Tooltip title={`${pct(u, { sign: false })} consumed${fu !== null ? ` · forecast ${pct(fu, { sign: false })} of budget` : ""}`}>
      <Box sx={{ position: "relative", width: "100%", minWidth: 80 }} data-testid={testId}>
        <LinearProgress variant="determinate" value={Math.min(u, 100)} aria-label={label} sx={{ height: 8, bgcolor: "#e3eefb", "& .MuiLinearProgress-bar": { bgcolor: color } }} />
        {fu !== null && <Box aria-hidden sx={{ position: "absolute", top: -3, bottom: -3, left: `${Math.min(fu, 100)}%`, width: 2, bgcolor: fu > 100 ? "#d03b3b" : "#52514e" }} />}
      </Box>
    </Tooltip>
  );
}

export { compactMoney, money };
