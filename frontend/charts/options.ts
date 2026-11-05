/**
 * ECharts option builders. All builders consume the same API payloads used by the tables,
 * so every visualisation of a view is derived from one query result.
 *
 * Mark specs (dataviz guidance): bars <= 24px with 4px rounded data-ends and a 2px surface gap,
 * 2px lines, hairline solid gridlines, one value axis (never dual-axis), legend for >= 2 series,
 * categorical colour by entity (lib/colors), text never in series colour, tooltip text escaped.
 */
import type { EChartsOption } from "./EChart";
import { bucketLabel, compactMoney, escapeHtml, money, pct } from "@/lib/format";
import { assignColors } from "@/lib/colors";
import type { GroupItem, Series, Waterfall } from "@/lib/types";
import { brand, fontStack, ink, polarity, previousColor, surface } from "@/styles/tokens";

const MAX_CATEGORIES = 8;

const tooltipBase = {
  backgroundColor: "#ffffff",
  borderColor: surface.border,
  borderWidth: 1,
  padding: [8, 10],
  textStyle: { color: ink.primary, fontSize: 12, fontFamily: fontStack },
  extraCssText: "box-shadow: 0 4px 14px rgba(16,24,40,0.10); border-radius: 6px;",
  confine: true,
};

function axisValue(currency: string) {
  return {
    type: "value",
    axisLabel: { color: ink.axis, fontSize: 11, formatter: (v: number) => compactMoney(v, currency) },
    splitLine: { lineStyle: { color: ink.grid, width: 1, type: "solid" } },
    axisLine: { show: false },
    axisTick: { show: false },
  };
}

function axisCategory(labels: string[], rotate = 0) {
  return {
    type: "category",
    data: labels,
    axisLabel: { color: ink.axis, fontSize: 11, rotate, hideOverlap: true, formatter: (v: string) => (v.length > 22 ? `${v.slice(0, 21)}…` : v) },
    axisLine: { lineStyle: { color: ink.baseline } },
    axisTick: { show: false },
  };
}

function base(extra: Record<string, unknown> = {}): EChartsOption {
  return {
    animationDuration: 250,
    animationDurationUpdate: 200,
    textStyle: { fontFamily: fontStack },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    ...extra,
  };
}

function legend(show: boolean) {
  return show
    ? { show: true, top: 0, left: 0, type: "scroll", icon: "roundRect", itemWidth: 10, itemHeight: 10, itemGap: 14, textStyle: { color: ink.secondary, fontSize: 11.5 } }
    : { show: false };
}

function dot(color: string) {
  return `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color};margin-right:6px"></span>`;
}

/** Fold groups beyond the categorical palette into one "Other" entry (keeps totals exact). */
export function foldGroups(groups: GroupItem[], max = MAX_CATEGORIES): GroupItem[] {
  const sorted = [...groups].sort((a, b) => b.current - a.current);
  if (sorted.length <= max) return sorted;
  const keep = sorted.slice(0, max);
  const rest = sorted.slice(max);
  keep.push({
    key: "__other__",
    label: `Other (${rest.length})`,
    current: rest.reduce((s, g) => s + g.current, 0),
    previous: rest.reduce((s, g) => s + (g.previous ?? 0), 0),
  });
  return keep;
}

// --------------------------------------------------------------------------- bar ---
export function barOption(groups: GroupItem[], opts: { currency: string; grouped: boolean; hasComparison: boolean; max?: number }): EChartsOption {
  const max = opts.max ?? 20;
  const sorted = [...groups].filter((g) => g.key !== "__other__").sort((a, b) => b.current - a.current).slice(0, max);
  const labels = sorted.map((g) => g.label);
  const grouped = opts.grouped && opts.hasComparison;
  const barStyle = { borderRadius: [4, 4, 0, 0] };
  const series: unknown[] = [];
  if (grouped) {
    series.push({ name: "Previous period", type: "bar", barMaxWidth: 24, barGap: "12%", data: sorted.map((g) => g.previous ?? 0), itemStyle: { ...barStyle, color: previousColor } });
  }
  series.push({
    name: "Current period",
    type: "bar",
    barMaxWidth: 24,
    data: sorted.map((g) => ({ value: g.current, key: g.key })),
    itemStyle: { ...barStyle, color: brand.primary },
    emphasis: { itemStyle: { color: "#0c5799" } },
    label: grouped ? { show: false } : { show: sorted.length <= 10, position: "top", color: ink.secondary, fontSize: 11, formatter: (p: { value: number }) => compactMoney(p.value, opts.currency) },
  });
  return base({
    legend: legend(grouped),
    // rotated category labels extend left of the first bar; reserve room so the first one is not clipped
    grid: { left: labels.length > 4 ? 64 : 8, right: 16, top: grouped ? 36 : 24, bottom: 8, containLabel: true },
    tooltip: {
      ...tooltipBase,
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(15,108,189,0.06)" } },
      formatter: (ps: { dataIndex: number }[]) => {
        const g = sorted[ps[0].dataIndex];
        let h = `<b>${escapeHtml(g.label)}</b><br/>${dot(brand.primary)}Current: <b>${money(g.current, opts.currency)}</b>`;
        if (opts.hasComparison) {
          h += `<br/>${dot(previousColor)}Previous: ${money(g.previous ?? 0, opts.currency)}`;
          h += `<br/>Change: <b>${money(g.diff ?? 0, opts.currency, { sign: true })}</b> (${g.pct === null || g.pct === undefined ? (g.status === "new" ? "new" : "n/a") : pct(g.pct)})`;
        }
        if (g.share_of_total !== null && g.share_of_total !== undefined) h += `<br/><span style="color:${ink.muted}">${pct(g.share_of_total, { sign: false })} of total</span>`;
        return h;
      },
    },
    xAxis: axisCategory(labels, labels.length > 4 ? 30 : 0),
    yAxis: axisValue(opts.currency),
    series,
  });
}

// ----------------------------------------------------------------- time series ---
interface TimeOpts {
  currency: string;
  stacked: boolean;
  area: boolean;
  kind: "bar" | "line";
  byGroup: boolean;
  dimension: string;
  showPrevious?: boolean;
  zoom?: boolean;
}

/** A bucket only partly inside the period (e.g. the current month) is marked so a partial total never reads as a cost drop. */
function isPartial(s: Series, i: number): boolean {
  const c = s.coverage?.[i];
  return !!c && c[0] < c[1];
}

function partialNote(s: Series, i: number): string {
  const c = s.coverage?.[i];
  return c && c[0] < c[1] ? `<br/><span style="color:${ink.muted}">Partial period: ${c[0]} of ${c[1]} days</span>` : "";
}

export function timeSeriesOption(s: Series, opts: TimeOpts): EChartsOption {
  const labels = s.buckets.map((b, i) => `${bucketLabel(b, s.granularity)}${isPartial(s, i) ? "*" : ""}`);
  const fade = (values: number[]) => values.map((v, i) => (isPartial(s, i) && s.granularity !== "daily" ? { value: v, itemStyle: { opacity: 0.45 } } : v));
  const series: unknown[] = [];
  const keys = opts.byGroup ? s.series.map((x) => x.key) : [];
  const colors = assignColors(opts.dimension, keys);
  if (opts.byGroup && s.series.length) {
    s.series.forEach((x, i) => {
      const color = colors[x.key];
      const isLast = i === s.series.length - 1;
      if (opts.kind === "bar") {
        series.push({
          name: x.label,
          type: "bar",
          stack: opts.stacked ? "total" : undefined,
          barMaxWidth: 24,
          data: fade(x.values),
          itemStyle: { color, borderColor: surface.card, borderWidth: opts.stacked ? 1 : 0, borderRadius: opts.stacked ? (isLast ? [4, 4, 0, 0] : 0) : [4, 4, 0, 0] },
          emphasis: { focus: "series" },
        });
      } else {
        series.push({
          name: x.label,
          type: "line",
          stack: opts.stacked ? "total" : undefined,
          smooth: false,
          symbol: "circle",
          symbolSize: 6,
          showSymbol: s.buckets.length <= 31,
          lineStyle: { width: 2, color },
          itemStyle: { color, borderColor: surface.card, borderWidth: 2 },
          areaStyle: opts.area ? { color, opacity: opts.stacked ? 0.32 : 0.1 } : undefined,
          emphasis: { focus: "series" },
          data: x.values,
        });
      }
    });
  } else {
    series.push(
      opts.kind === "bar"
        ? { name: "Current period", type: "bar", barMaxWidth: 24, data: fade(s.total), itemStyle: { color: brand.primary, borderRadius: [4, 4, 0, 0] } }
        : {
            name: "Current period",
            type: "line",
            symbol: "circle",
            symbolSize: 7,
            showSymbol: s.buckets.length <= 45,
            lineStyle: { width: 2, color: brand.primary },
            itemStyle: { color: brand.primary, borderColor: surface.card, borderWidth: 2 },
            areaStyle: opts.area ? { color: brand.primary, opacity: 0.1 } : undefined,
            data: s.total,
          },
    );
  }
  if (opts.showPrevious !== false && s.previous_total && !opts.stacked) {
    series.push({
      name: "Previous period",
      type: "line",
      symbol: "none",
      lineStyle: { width: 2, color: previousColor },
      itemStyle: { color: previousColor },
      data: s.previous_total,
      z: 1,
    });
  }
  const seriesCount = series.length;
  return base({
    legend: legend(seriesCount >= 2),
    grid: { left: 8, right: 16, top: seriesCount >= 2 ? 36 : 20, bottom: opts.zoom ? 44 : 8, containLabel: true },
    tooltip: {
      ...tooltipBase,
      trigger: "axis",
      axisPointer: { type: opts.kind === "bar" ? "shadow" : "line", lineStyle: { color: ink.baseline }, shadowStyle: { color: "rgba(15,108,189,0.06)" } },
      formatter: (ps: { dataIndex: number; seriesName: string; value: number | null; color: string }[]) => {
        const i = ps[0].dataIndex;
        let h = `<b>${escapeHtml(labels[i])}</b>`;
        if (s.previous_buckets?.[i] && s.previous_total) h += `<span style="color:${ink.muted}"> vs ${escapeHtml(bucketLabel(s.previous_buckets[i] as string, s.granularity))}</span>`;
        const rows = [...ps].filter((p) => p.value !== null && p.value !== undefined).sort((a, b) => (b.value as number) - (a.value as number));
        for (const p of rows.slice(0, 12)) h += `<br/>${dot(p.color)}${escapeHtml(p.seriesName)}: <b>${money(p.value as number, opts.currency)}</b>`;
        if (opts.byGroup && opts.stacked) h += `<br/><span style="color:${ink.muted}">Total: ${money(s.total[i], opts.currency)}</span>`;
        return h + partialNote(s, i);
      },
    },
    xAxis: { ...axisCategory(labels), boundaryGap: opts.kind === "bar" },
    yAxis: axisValue(opts.currency),
    dataZoom: opts.zoom ? [{ type: "inside" }, { type: "slider", height: 18, bottom: 6, borderColor: surface.border, fillerColor: "rgba(15,108,189,0.08)", handleSize: 14 }] : undefined,
    series,
  });
}

// ------------------------------------------------------------------- waterfall ---
export function waterfallOption(w: Waterfall, currency: string): EChartsOption {
  const steps = w.steps;
  const labels = steps.map((s) => s.label);
  const ends = steps.flatMap((s) => [s.start, s.end]).filter((v) => v > 0);
  const lo = Math.min(...steps.filter((s) => s.kind !== "start" && s.kind !== "end").flatMap((s) => [s.start, s.end]), w.previous_total, w.current_total);
  const hi = Math.max(...ends, w.previous_total, w.current_total);
  const range = Math.max(hi - lo, Math.abs(hi) * 0.02, 1);
  const mag = Math.pow(10, Math.floor(Math.log10(range)));
  const axisMin = Math.max(0, Math.floor((lo - range * 0.5) / mag) * mag);
  const colorOf = (k: string) => (k === "increase" ? polarity.increase : k === "decrease" ? polarity.decrease : k === "other" ? polarity.other : polarity.total);
  const placeholder = steps.map((s) => (s.kind === "start" || s.kind === "end" ? 0 : Math.min(s.start, s.end)));
  const values = steps.map((s) => ({
    value: s.kind === "start" || s.kind === "end" ? s.value : Math.abs(s.value),
    itemStyle: { color: s.kind === "other" && s.value < 0 ? polarity.decrease : colorOf(s.kind), borderRadius: [4, 4, 0, 0] },
    key: s.key,
  }));
  return base({
    grid: { left: labels.length > 6 ? 64 : 8, right: 16, top: 28, bottom: 8, containLabel: true },
    tooltip: {
      ...tooltipBase,
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(15,108,189,0.06)" } },
      formatter: (ps: { dataIndex: number }[]) => {
        const s = steps[ps[0].dataIndex];
        if (s.kind === "start" || s.kind === "end") return `<b>${escapeHtml(s.label)}</b><br/>${money(s.value, currency)}`;
        let h = `<b>${escapeHtml(s.label)}</b><br/>Contribution: <b>${money(s.value, currency, { sign: true })}</b>`;
        h += `<br/>Previous: ${money(s.previous, currency)}<br/>Current: ${money(s.current, currency)}`;
        if (s.pct !== null) h += `<br/>Change: ${pct(s.pct)}`;
        if (s.status === "new") h += `<br/><i>New in this period</i>`;
        h += `<br/><span style="color:${ink.muted}">Running total ${money(s.start, currency)} → ${money(s.end, currency)}</span>`;
        return h;
      },
    },
    xAxis: axisCategory(labels, labels.length > 6 ? 25 : 0),
    yAxis: { ...axisValue(currency), min: axisMin, scale: true },
    series: [
      { name: "base", type: "bar", stack: "wf", silent: true, itemStyle: { color: "transparent" }, emphasis: { disabled: true }, data: placeholder, barMaxWidth: 40, tooltip: { show: false } },
      {
        name: "Change",
        type: "bar",
        stack: "wf",
        barMaxWidth: 40,
        data: values,
        label: {
          show: true,
          position: "top",
          color: ink.secondary,
          fontSize: 11,
          formatter: (p: { dataIndex: number }) => {
            const s = steps[p.dataIndex];
            return s.kind === "start" || s.kind === "end" ? compactMoney(s.value, currency) : `${s.value >= 0 ? "+" : ""}${compactMoney(s.value, currency)}`;
          },
        },
      },
    ],
  });
}

// ------------------------------------------------------------------ donut/tree ---
export function donutOption(groups: GroupItem[], opts: { currency: string; dimension: string }): EChartsOption {
  const folded = foldGroups(groups.filter((g) => g.current > 0));
  const colors = assignColors(opts.dimension, folded.map((g) => g.key));
  const total = folded.reduce((s, g) => s + g.current, 0);
  return base({
    legend: { ...legend(true), orient: "vertical", left: "58%", top: "middle", formatter: (name: string) => (name.length > 30 ? `${name.slice(0, 29)}…` : name) },
    tooltip: {
      ...tooltipBase,
      trigger: "item",
      formatter: (p: { data: { key: string; name: string; value: number }; percent: number }) =>
        `<b>${escapeHtml(p.data.name)}</b><br/>${money(p.data.value, opts.currency)} · ${pct(p.percent, { sign: false })} of total`,
    },
    title: { text: compactMoney(total, opts.currency), subtext: "Total", left: "28%", top: "43%", textAlign: "center", textStyle: { fontSize: 18, fontWeight: 600, color: ink.primary }, subtextStyle: { color: ink.muted, fontSize: 11 } },
    series: [
      {
        type: "pie",
        radius: ["52%", "78%"],
        center: ["29%", "52%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: surface.card, borderWidth: 2, borderRadius: 3 },
        label: { show: false },
        data: folded.map((g) => ({ name: g.label, value: g.current, key: g.key, itemStyle: { color: colors[g.key] } })),
      },
    ],
  });
}

export function treemapOption(groups: GroupItem[], opts: { currency: string; dimension: string }): EChartsOption {
  const folded = foldGroups(groups.filter((g) => g.current > 0));
  const colors = assignColors(opts.dimension, folded.map((g) => g.key));
  const total = folded.reduce((s, g) => s + g.current, 0) || 1;
  return base({
    tooltip: {
      ...tooltipBase,
      formatter: (p: { data: { name: string; value: number } }) => `<b>${escapeHtml(p.data.name)}</b><br/>${money(p.data.value, opts.currency)} · ${pct((p.data.value / total) * 100, { sign: false })}`,
    },
    series: [
      {
        type: "treemap",
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        top: 4,
        left: 4,
        right: 4,
        bottom: 4,
        itemStyle: { borderColor: surface.card, borderWidth: 2, gapWidth: 2, borderRadius: 3 },
        label: {
          show: true,
          color: "#ffffff",
          fontSize: 12,
          overflow: "truncate",
          formatter: (p: { name: string; value: number }) => `${p.name}\n${compactMoney(p.value, opts.currency)}`,
        },
        data: folded.map((g) => ({ name: g.label, value: g.current, key: g.key, itemStyle: { color: colors[g.key] }, label: { color: colors[g.key] === "#eda100" ? "#0b0b0b" : "#ffffff" } })),
      },
    ],
  });
}

// --------------------------------------------------------------- executive trend ---
export function trendOption(
  s: Series & { budget?: (number | null)[] | null; forecast?: { points: { date: string; value: number }[]; method_label: string } | null },
  currency: string,
): EChartsOption {
  const fcPoints = s.forecast?.points ?? [];
  const allBuckets = [...s.buckets, ...fcPoints.map((p) => p.date).filter((d) => !s.buckets.includes(d))];
  const labels = allBuckets.map((b, i) => `${bucketLabel(b, s.granularity)}${i < s.buckets.length && isPartial(s, i) ? "*" : ""}`);
  const pad = (arr: (number | null)[]) => [...arr, ...Array(allBuckets.length - arr.length).fill(null)];
  const series: unknown[] = [
    {
      name: "Actual cost",
      type: "line",
      symbol: "circle",
      symbolSize: 6,
      showSymbol: false,
      lineStyle: { width: 2, color: brand.primary },
      itemStyle: { color: brand.primary, borderColor: surface.card, borderWidth: 2 },
      areaStyle: { color: brand.primary, opacity: 0.1 },
      data: pad(s.total),
    },
  ];
  if (s.previous_total) series.push({ name: "Previous period", type: "line", symbol: "none", lineStyle: { width: 2, color: previousColor }, itemStyle: { color: previousColor }, data: pad(s.previous_total) });
  if (s.budget) {
    const budgetAll = [...s.budget];
    if (fcPoints.length && s.granularity === "daily") {
      const dailyBudget = s.budget[s.budget.length - 1];
      fcPoints.forEach(() => budgetAll.push(dailyBudget));
    }
    series.push({ name: s.granularity === "daily" ? "Budget (daily pace)" : "Budget", type: "line", step: "middle", symbol: "none", lineStyle: { width: 2, color: ink.secondary }, itemStyle: { color: ink.secondary }, data: pad(budgetAll) });
  }
  if (fcPoints.length) {
    const fc = Array(s.buckets.length - 1).fill(null);
    fc.push(s.total[s.total.length - 1]);
    fcPoints.forEach((p) => fc.push(p.value));
    series.push({
      name: "Forecast (projection)",
      type: "line",
      symbol: "none",
      lineStyle: { width: 2, color: "#eb6834" },
      itemStyle: { color: "#eb6834" },
      data: fc.slice(0, allBuckets.length),
      markArea: { silent: true, itemStyle: { color: "rgba(235,104,52,0.05)" }, data: [[{ xAxis: labels[s.buckets.length] ?? labels[labels.length - 1] }, { xAxis: labels[labels.length - 1] }]] },
    });
  }
  return base({
    legend: legend(series.length >= 2),
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      ...tooltipBase,
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: ink.baseline } },
      formatter: (ps: { dataIndex: number; seriesName: string; value: number | null; color: string }[]) => {
        const i = ps[0].dataIndex;
        let h = `<b>${escapeHtml(labels[i])}</b>`;
        for (const p of ps) if (p.value !== null && p.value !== undefined) h += `<br/>${dot(p.color)}${escapeHtml(p.seriesName)}: <b>${money(p.value, currency)}</b>`;
        return i < s.buckets.length ? h + partialNote(s, i) : h;
      },
    },
    xAxis: { ...axisCategory(labels), boundaryGap: false },
    yAxis: axisValue(currency),
    series,
  });
}

export function sparklineOption(values: number[], highlightLast = true): EChartsOption {
  return {
    animation: false,
    grid: { left: 0, right: 2, top: 2, bottom: 2 },
    xAxis: { type: "category", show: false, data: values.map((_, i) => i) },
    yAxis: { type: "value", show: false, scale: true },
    tooltip: { show: false },
    series: [
      {
        type: "line",
        data: values,
        symbol: "circle",
        symbolSize: (_v: number, p: { dataIndex: number }) => (highlightLast && p.dataIndex === values.length - 1 ? 6 : 0),
        lineStyle: { width: 1.5, color: "#9aa7b5" },
        itemStyle: { color: brand.primary, borderColor: "#fff", borderWidth: 1.5 },
        areaStyle: { color: "#9aa7b5", opacity: 0.08 },
      },
    ],
  };
}
