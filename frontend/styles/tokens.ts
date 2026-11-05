/**
 * Design tokens. Chart colours follow the validated reference palette (dataviz skill):
 * categorical slots are assigned in fixed order and never cycled; a 9th series folds
 * into "Other". Status colours are reserved and always paired with an icon + label.
 */
export const surface = {
  page: "#f4f5f7",
  card: "#ffffff",
  subtle: "#f8f9fb",
  border: "#e1e4e8",
  borderStrong: "#c9ced6",
  hover: "#f1f5fb",
  selected: "#e8f1fc",
};

export const ink = {
  primary: "#1b1f24",
  secondary: "#52514e",
  muted: "#6b6f76",
  axis: "#898781",
  grid: "#e9e8e3",
  baseline: "#c3c2b7",
};

export const brand = {
  primary: "#0f6cbd", // Azure / Fluent brand blue
  primaryDark: "#0c5799",
  primaryLight: "#ebf3fc",
  nav: "#1b2a3a",
};

export const categorical = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
export const otherColor = "#b4b6b9";
export const previousColor = "#9aa0a6";

/** Diverging pair (polarity) used for cost increases / decreases in waterfalls. */
export const polarity = { increase: "#e34948", decrease: "#2a78d6", total: "#52514e", other: "#a3a7ad" };

export const status = {
  good: "#0ca30c",
  goodText: "#006300",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
  info: "#2a78d6",
  neutral: "#6b6f76",
};

export const severityColor: Record<string, string> = {
  critical: status.critical,
  high: status.serious,
  medium: status.warning,
  low: "#7aa7d9",
  informational: "#a3a7ad",
};

export const fontStack = 'system-ui, -apple-system, "Segoe UI", "Segoe UI Variable", Roboto, "Helvetica Neue", Arial, sans-serif';
