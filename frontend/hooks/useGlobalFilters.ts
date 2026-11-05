"use client";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import type { Params } from "@/lib/api";
import { useUrlState } from "./useUrlState";

export const GLOBAL_KEYS = ["app", "env", "sub", "preset", "start", "end", "cost", "cur"] as const;

export const GLOBAL_DEFAULTS = {
  app: "",
  env: "",
  sub: "",
  preset: "last_30_days",
  start: "",
  end: "",
  cost: "actual",
  cur: "",
};

export type GlobalFilters = typeof GLOBAL_DEFAULTS;

/** Global filters (application, environment, subscription, date range, cost type, currency) live in the URL. */
export function useGlobalFilters() {
  const [filters, setFilters] = useUrlState(GLOBAL_DEFAULTS);
  const apiParams = useMemo<Params>(() => toApiParams(filters), [filters]);
  return { filters, setFilters, apiParams };
}

export function toApiParams(f: GlobalFilters): Params {
  return {
    application: f.app ? f.app.split(",") : undefined,
    environment: f.env ? f.env.split(",") : undefined,
    subscription: f.sub ? f.sub.split(",") : undefined,
    preset: f.preset,
    start_date: f.preset === "custom" ? f.start : undefined,
    end_date: f.preset === "custom" ? f.end : undefined,
    cost_type: f.cost,
    currency: f.cur || undefined,
  };
}

/** Build an internal link that keeps the current global filters. */
export function useLinkWithFilters() {
  const sp = useSearchParams();
  return (path: string, extra?: Record<string, string | undefined>) => {
    const next = new URLSearchParams();
    for (const k of GLOBAL_KEYS) {
      const v = sp.get(k);
      if (v) next.set(k, v);
    }
    if (extra) for (const [k, v] of Object.entries(extra)) if (v) next.set(k, v);
    const q = next.toString();
    return q ? `${path}?${q}` : path;
  };
}
