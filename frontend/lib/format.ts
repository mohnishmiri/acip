/** Number, currency, percentage and date formatting. Values are already rounded by the API. */

export function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);
}

const fmtCache = new Map<string, Intl.NumberFormat>();
function nf(key: string, opts: Intl.NumberFormatOptions): Intl.NumberFormat {
  let f = fmtCache.get(key);
  if (!f) {
    f = new Intl.NumberFormat("en-US", opts);
    fmtCache.set(key, f);
  }
  return f;
}

export function money(value: number | null | undefined, currency = "USD", opts: { decimals?: number; sign?: boolean } = {}): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const d = opts.decimals ?? 2;
  const s = nf(`m-${currency}-${d}`, { style: "currency", currency, minimumFractionDigits: d, maximumFractionDigits: d }).format(Math.abs(value));
  if (value < 0) return `-${s}`;
  return opts.sign && value > 0 ? `+${s}` : s;
}

export function compactMoney(value: number | null | undefined, currency = "USD"): string {
  if (value === null || value === undefined) return "—";
  const abs = Math.abs(value);
  const s = abs >= 1000 ? nf(`c-${currency}`, { style: "currency", currency, notation: "compact", maximumFractionDigits: abs >= 1e6 ? 2 : 1 }).format(abs) : money(abs, currency, { decimals: 0 });
  return value < 0 ? `-${s}` : s;
}

export function compactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return nf("cn", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function num(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return "—";
  return nf(`n-${decimals}`, { minimumFractionDigits: 0, maximumFractionDigits: decimals }).format(value);
}

export function pct(value: number | null | undefined, opts: { sign?: boolean; decimals?: number } = {}): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const d = opts.decimals ?? 1;
  const s = `${nf(`p-${d}`, { minimumFractionDigits: d, maximumFractionDigits: d }).format(Math.abs(value))}%`;
  if (value < 0) return `-${s}`;
  return opts.sign !== false && value > 0 ? `+${s}` : s;
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" });
}

export function longDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" })} ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })} UTC`;
}

export function bucketLabel(iso: string, granularity: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (granularity === "monthly") return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" });
  if (granularity === "weekly") return `Wk ${d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" })}`;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" });
}

export function periodText(p?: { start: string; end: string } | null): string {
  if (!p) return "—";
  return p.start === p.end ? longDate(p.start) : `${shortDate(p.start)} – ${longDate(p.end)}`;
}

export function titleCase(s: string | null | undefined): string {
  if (!s) return "—";
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
