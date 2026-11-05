import { getDevRole, getToken } from "./auth";

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  requestId?: string | null;
  constructor(status: number, code: string, message: string, details?: unknown, requestId?: string | null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export type ParamValue = string | number | boolean | null | undefined | (string | number)[];
export type Params = Record<string, ParamValue>;

export function toQuery(params?: Params): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.append(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function headers(json: boolean): Promise<HeadersInit> {
  const h: Record<string, string> = { Accept: "application/json" };
  if (json) h["Content-Type"] = "application/json";
  const token = await getToken();
  if (token) h.Authorization = `Bearer ${token}`;
  const devRole = getDevRole();
  if (devRole) h["X-ACIP-Dev-Role"] = devRole;
  return h;
}

export async function api<T>(path: string, opts: { params?: Params; method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const res = await fetch(`/api/v1${path}${toQuery(opts.params)}`, {
    method: opts.method ?? "GET",
    headers: await headers(opts.body !== undefined),
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
    cache: "no-store",
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const e = data?.error ?? {};
    throw new ApiError(res.status, e.code ?? "error", e.message ?? `Request failed (${res.status})`, e.details, e.request_id ?? res.headers.get("x-request-id"));
  }
  return data as T;
}

export async function download(path: string, params?: Params): Promise<void> {
  const res = await fetch(`/api/v1${path}${toQuery(params)}`, { headers: await headers(false) });
  if (!res.ok) {
    let msg = `Export failed (${res.status})`;
    try {
      msg = (await res.json()).error?.message ?? msg;
    } catch {
      /* non-JSON */
    }
    throw new ApiError(res.status, "export_failed", msg);
  }
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const name = /filename="?([^";]+)"?/.exec(cd)?.[1] ?? "acip-export";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
