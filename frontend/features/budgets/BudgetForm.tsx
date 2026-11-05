"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { Box, Button, Chip, Grid, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useRef, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { api } from "@/lib/api";
import { useFilterOptions } from "@/services/queries";
import { errorMessage, FormDialog, RhfSelect, RhfSwitch, RhfText } from "@/features/admin/ui";

export const budgetSchema = z
  .object({
    name: z.string().trim().min(1, "Name is required").max(200),
    scope_type: z.enum(["total", "application", "subscription", "environment", "resource_group"]),
    scope_ref: z.string(),
    period_type: z.enum(["monthly", "annual"]),
    amount: z.number({ error: "Enter an amount" }).positive("Amount must be greater than zero"),
    currency: z.string().regex(/^[A-Z]{3}$/, "Use a 3-letter ISO currency code"),
    cost_type: z.enum(["actual", "amortized"]),
    start_date: z.string().min(1, "Start date is required"),
    end_date: z.string(),
    thresholds: z.array(z.number().min(1).max(500)).min(1, "Add at least one threshold"),
    forecast_alert: z.boolean(),
    enabled: z.boolean(),
    notes: z.string().max(2000),
  })
  .refine((v) => v.scope_type === "total" || v.scope_ref.trim().length > 0, { path: ["scope_ref"], message: "Select the scope" })
  .refine((v) => !v.end_date || v.end_date >= v.start_date, { path: ["end_date"], message: "End date must be on or after the start date" });

export type BudgetFormValues = z.infer<typeof budgetSchema>;

export interface BudgetLike {
  id: number;
  name: string;
  scope_type: string;
  scope_ref: string | null;
  period_type: string;
  amount: number;
  currency: string;
  cost_type: string;
  start_date: string;
  end_date: string | null;
  thresholds: number[];
  forecast_alert: boolean;
  enabled: boolean;
  notes: string | null;
}

const SCOPE_TYPES = [
  { value: "total", label: "All subscriptions (total)" },
  { value: "application", label: "Application" },
  { value: "subscription", label: "Subscription" },
  { value: "environment", label: "Environment (Production / Non-Production)" },
  { value: "resource_group", label: "Resource group" },
];

export function BudgetForm({ open, budget, onClose, onSaved }: { open: boolean; budget: BudgetLike | null; onClose: () => void; onSaved: (msg: string) => void }) {
  const opts = useFilterOptions();
  const [error, setError] = useState<string | null>(null);
  const [newThreshold, setNewThreshold] = useState("");
  const defaults = useMemo<BudgetFormValues>(
    () => ({
      name: budget?.name ?? "",
      scope_type: (budget?.scope_type as BudgetFormValues["scope_type"]) ?? "total",
      scope_ref: budget?.scope_ref ?? "",
      period_type: (budget?.period_type as BudgetFormValues["period_type"]) ?? "monthly",
      amount: budget?.amount ?? (undefined as unknown as number),
      currency: budget?.currency ?? opts.data?.default_currency ?? "USD",
      cost_type: (budget?.cost_type as BudgetFormValues["cost_type"]) ?? "actual",
      start_date: budget?.start_date ?? `${new Date().getUTCFullYear()}-01-01`,
      end_date: budget?.end_date ?? "",
      thresholds: budget?.thresholds?.map(Number) ?? [70, 80, 90, 100],
      forecast_alert: budget?.forecast_alert ?? true,
      enabled: budget?.enabled ?? true,
      notes: budget?.notes ?? "",
    }),
    [budget, opts.data?.default_currency],
  );
  const { control, handleSubmit, reset, setValue, formState } = useForm<BudgetFormValues>({ resolver: zodResolver(budgetSchema), defaultValues: defaults });
  const scopeType = useWatch({ control, name: "scope_type" });
  const prevScope = useRef<string | null>(null);
  useEffect(() => {
    // clear the scope reference when the user changes scope type (not on initial load / edit)
    if (prevScope.current !== null && prevScope.current !== scopeType) setValue("scope_ref", "");
    prevScope.current = scopeType;
  }, [scopeType, setValue]);
  useEffect(() => {
    if (open) {
      prevScope.current = null;
      reset(defaults);
      setError(null);
    }
  }, [open, defaults, reset]);

  const scopeOptions = useMemo(() => {
    const o = opts.data;
    if (!o) return [];
    if (scopeType === "application") return o.applications.map((a) => ({ value: String(a.id), label: a.name }));
    if (scopeType === "subscription") return o.subscriptions.map((s) => ({ value: s.subscription_id, label: s.subscription_name }));
    if (scopeType === "environment") return o.environment_groups.map((g) => ({ value: g.code, label: g.name }));
    if (scopeType === "resource_group") return o.resource_groups.map((r) => ({ value: r, label: r }));
    return [];
  }, [opts.data, scopeType]);

  const submit = handleSubmit(async (v) => {
    setError(null);
    const body = { ...v, scope_ref: v.scope_type === "total" ? null : v.scope_ref, end_date: v.end_date || null, notes: v.notes || null };
    try {
      if (budget) await api(`/budgets/${budget.id}`, { method: "PUT", body });
      else await api("/budgets", { method: "POST", body });
      onSaved(budget ? "Budget updated" : "Budget created");
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  return (
    <FormDialog open={open} title={budget ? `Edit budget — ${budget.name}` : "New budget"} onClose={onClose} onSubmit={submit} busy={formState.isSubmitting} error={error} maxWidth="md" testId="budget-dialog">
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 7 }}>
          <RhfText control={control} name="name" label="Budget name" required testId="budget-name" />
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <RhfSelect control={control} name="period_type" label="Period" options={[{ value: "monthly", label: "Monthly" }, { value: "annual", label: "Annual" }]} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSelect control={control} name="scope_type" label="Scope type" options={SCOPE_TYPES} testId="budget-scope-type" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSelect control={control} name="scope_ref" label="Scope" options={scopeOptions} disabled={scopeType === "total"} helperText={scopeType === "total" ? "Applies to all registered subscriptions" : undefined} testId="budget-scope-ref" />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <RhfText control={control} name="amount" label="Amount" type="number" required testId="budget-amount" />
        </Grid>
        <Grid size={{ xs: 6, md: 4 }}>
          <RhfText control={control} name="currency" label="Currency" helperText="Billing currency (no conversion is applied)" />
        </Grid>
        <Grid size={{ xs: 6, md: 4 }}>
          <RhfSelect control={control} name="cost_type" label="Cost type" options={[{ value: "actual", label: "Actual cost" }, { value: "amortized", label: "Amortized cost" }]} />
        </Grid>
        <Grid size={{ xs: 6 }}>
          <RhfText control={control} name="start_date" label="Start date" type="date" required />
        </Grid>
        <Grid size={{ xs: 6 }}>
          <RhfText control={control} name="end_date" label="End date (optional)" type="date" />
        </Grid>
        <Grid size={{ xs: 12 }}>
          <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
            Alert thresholds (% of budget consumed)
          </Typography>
          <Controller
            control={control}
            name="thresholds"
            render={({ field, fieldState }) => (
              <Box>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                  {[...field.value].sort((a, b) => a - b).map((t) => (
                    <Chip key={t} label={`${t}%`} onDelete={() => field.onChange(field.value.filter((x) => x !== t))} variant="outlined" />
                  ))}
                  <TextField
                    size="small"
                    type="number"
                    placeholder="Add %"
                    value={newThreshold}
                    onChange={(e) => setNewThreshold(e.target.value)}
                    sx={{ width: 110 }}
                    slotProps={{ htmlInput: { min: 1, max: 500, "aria-label": "New threshold percentage" } }}
                  />
                  <Button
                    size="small"
                    onClick={() => {
                      const n = Number(newThreshold);
                      if (n > 0 && n <= 500 && !field.value.includes(n)) field.onChange([...field.value, n]);
                      setNewThreshold("");
                    }}
                  >
                    Add
                  </Button>
                </Stack>
                {fieldState.error && (
                  <Typography variant="caption" color="error">
                    {fieldState.error.message}
                  </Typography>
                )}
              </Box>
            )}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSwitch control={control} name="forecast_alert" label="Alert when the forecast is expected to exceed the budget" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RhfSwitch control={control} name="enabled" label="Budget enabled" />
        </Grid>
        <Grid size={{ xs: 12 }}>
          <RhfText control={control} name="notes" label="Notes" multiline />
        </Grid>
      </Grid>
    </FormDialog>
  );
}
