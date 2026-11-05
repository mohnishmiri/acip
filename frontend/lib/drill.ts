import { api, type Params } from "./api";

/** Group-by dimension -> API filter parameter (mirrors backend FILTER_PARAM). */
export const FILTER_PARAM: Record<string, string> = {
  application: "application",
  environment: "environment",
  subscription: "subscription",
  service_category: "service_category",
  resource_group: "resource_group",
  resource: "resource",
  resource_type: "resource_type",
  meter_category: "meter_category",
  meter_name: "meter_name",
  region: "region",
  sku: "sku",
  cost_center: "cost_center",
  owner: "owner",
  charge_type: "charge_type",
  pricing_model: "pricing_model",
  tag: "tag",
};

export const DIM_LABEL: Record<string, string> = {
  application: "Application",
  environment: "Environment",
  subscription: "Subscription",
  service_category: "Azure Service",
  resource_group: "Resource Group",
  resource: "Resource",
  resource_type: "Resource Type",
  meter_category: "Meter Category",
  meter_name: "Meter",
  region: "Region",
  sku: "SKU",
  cost_center: "Cost Center",
  owner: "Owner",
  charge_type: "Charge Type",
  pricing_model: "Pricing Model",
  tag: "Tag",
};

export interface DrillStep {
  dim: string;
  key: string;
  label: string;
  tagKey?: string;
  fromGroup?: string; // group-by that was active before this step (restored on back)
}

export function parseDrill(raw: string): DrillStep[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.filter((s) => s && typeof s.dim === "string" && typeof s.key === "string") : [];
  } catch {
    return [];
  }
}

/** Merge drill filters into API params (multiple steps on one dimension intersect -> last wins). */
export function drillParams(steps: DrillStep[]): Params {
  const out: Record<string, string[]> = {};
  for (const s of steps) {
    const p = FILTER_PARAM[s.dim];
    if (!p) continue;
    out[p] = [s.dim === "tag" ? `${s.tagKey}=${s.key}` : s.key];
  }
  return out;
}

const idCache = new Map<string, number | null>();

/** Resolve a resource key (ARM id) to the internal resource id used by the detail page. */
export async function resourceIdFor(key: string, params: Params): Promise<number | null> {
  if (idCache.has(key)) return idCache.get(key) ?? null;
  const res = await api<{ data: { id: number | null }[] }>("/resources", { params: { ...params, resource: [key], page_size: 1, preset: params.preset ?? "last_90_days" } });
  const id = res.data[0]?.id ?? null;
  idCache.set(key, id);
  return id;
}
