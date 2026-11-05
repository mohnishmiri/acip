"use client";
import BarChartIcon from "@mui/icons-material/BarChart";
import TableRowsOutlinedIcon from "@mui/icons-material/TableRowsOutlined";
import { Box, Paper, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from "@mui/material";
import { type ReactNode, useState } from "react";
import { surface } from "@/styles/tokens";

/** Card with a header; optional chart/table toggle so every chart has an exact-figures view. */
export function Section({
  title,
  subtitle,
  actions,
  children,
  table,
  defaultView = "chart",
  noPadding,
  testId,
  minHeight,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  table?: ReactNode;
  defaultView?: "chart" | "table";
  noPadding?: boolean;
  testId?: string;
  minHeight?: number;
}) {
  const [view, setView] = useState<"chart" | "table">(defaultView);
  return (
    <Paper variant="outlined" data-testid={testId} sx={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="h3" noWrap>
            {title}
          </Typography>
          {subtitle && (
            <Typography variant="caption" component="div" noWrap>
              {subtitle}
            </Typography>
          )}
        </Box>
        {actions}
        {table && (
          <ToggleButtonGroup size="small" exclusive value={view} onChange={(_, v) => v && setView(v)} aria-label="Chart or table view">
            <ToggleButton value="chart" aria-label="Chart view">
              <Tooltip title="Chart">
                <BarChartIcon sx={{ fontSize: 16 }} />
              </Tooltip>
            </ToggleButton>
            <ToggleButton value="table" aria-label="Table view">
              <Tooltip title="Table">
                <TableRowsOutlinedIcon sx={{ fontSize: 16 }} />
              </Tooltip>
            </ToggleButton>
          </ToggleButtonGroup>
        )}
      </Stack>
      <Box sx={{ p: noPadding || view === "table" ? 0 : 1.5, flex: 1, minWidth: 0 }}>{view === "table" && table ? table : children}</Box>
    </Paper>
  );
}
