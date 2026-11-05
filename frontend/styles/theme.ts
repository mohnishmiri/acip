"use client";
import { createTheme } from "@mui/material/styles";
import { brand, fontStack, ink, status, surface } from "./tokens";

export const theme = createTheme({
  cssVariables: true,
  palette: {
    mode: "light",
    primary: { main: brand.primary, dark: brand.primaryDark, light: brand.primaryLight, contrastText: "#fff" },
    secondary: { main: "#52514e" },
    error: { main: status.critical },
    warning: { main: "#b37400" },
    success: { main: status.goodText },
    info: { main: brand.primary },
    background: { default: surface.page, paper: surface.card },
    text: { primary: ink.primary, secondary: ink.secondary },
    divider: surface.border,
  },
  shape: { borderRadius: 4 },
  spacing: 8,
  typography: {
    fontFamily: fontStack,
    fontSize: 13,
    h1: { fontSize: 20, fontWeight: 600, letterSpacing: -0.1 },
    h2: { fontSize: 16, fontWeight: 600 },
    h3: { fontSize: 14, fontWeight: 600 },
    h4: { fontSize: 13, fontWeight: 600 },
    subtitle1: { fontSize: 13, fontWeight: 600 },
    subtitle2: { fontSize: 12, fontWeight: 600, color: ink.secondary },
    body1: { fontSize: 13 },
    body2: { fontSize: 12.5 },
    caption: { fontSize: 11.5, color: ink.muted },
    overline: { fontSize: 10.5, fontWeight: 600, letterSpacing: 0.6 },
    button: { textTransform: "none", fontWeight: 600, fontSize: 12.5 },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { backgroundColor: surface.page, fontVariantNumeric: "normal" },
        ".num": { fontVariantNumeric: "tabular-nums" },
      },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: { root: { backgroundImage: "none" }, outlined: { borderColor: surface.border } },
    },
    MuiCard: { defaultProps: { variant: "outlined" } },
    MuiButton: { defaultProps: { disableElevation: true, size: "small" }, styleOverrides: { root: { borderRadius: 4, paddingInline: 12 } } },
    MuiIconButton: { defaultProps: { size: "small" } },
    MuiTextField: { defaultProps: { size: "small" } },
    MuiSelect: { defaultProps: { size: "small" } },
    MuiFormControl: { defaultProps: { size: "small" } },
    MuiInputBase: { styleOverrides: { root: { fontSize: 12.5 } } },
    MuiOutlinedInput: { styleOverrides: { root: { backgroundColor: "#fff" }, notchedOutline: { borderColor: surface.borderStrong } } },
    MuiMenuItem: { styleOverrides: { root: { fontSize: 12.5, minHeight: 32 } } },
    MuiChip: { defaultProps: { size: "small" }, styleOverrides: { root: { borderRadius: 4, fontWeight: 600, fontSize: 11.5 } } },
    MuiTooltip: { defaultProps: { arrow: true }, styleOverrides: { tooltip: { fontSize: 11.5, backgroundColor: "#1b1f24" } } },
    MuiTabs: { styleOverrides: { root: { minHeight: 36 }, indicator: { height: 2 } } },
    MuiTab: { styleOverrides: { root: { minHeight: 36, textTransform: "none", fontWeight: 600, fontSize: 12.5, paddingInline: 12 } } },
    MuiToggleButton: { styleOverrides: { root: { textTransform: "none", fontSize: 12, fontWeight: 600, paddingBlock: 3, paddingInline: 10, borderColor: surface.borderStrong } } },
    MuiTableCell: {
      styleOverrides: {
        root: { fontSize: 12.5, borderColor: surface.border, paddingBlock: 6, paddingInline: 10 },
        head: { fontWeight: 600, color: ink.secondary, backgroundColor: surface.subtle, whiteSpace: "nowrap" },
      },
    },
    MuiAlert: { styleOverrides: { root: { fontSize: 12.5, alignItems: "center", paddingBlock: 2 } } },
    MuiDialogTitle: { styleOverrides: { root: { fontSize: 15, fontWeight: 600 } } },
    MuiLinearProgress: { styleOverrides: { root: { borderRadius: 2 } } },
  },
});
