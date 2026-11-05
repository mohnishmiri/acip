"use client";
import { Box, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

export function PageHeader({ title, subtitle, actions, children }: { title: string; subtitle?: ReactNode; actions?: ReactNode; children?: ReactNode }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Stack direction={{ xs: "column", md: "row" }} alignItems={{ md: "flex-end" }} spacing={1.5}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="h1">{title}</Typography>
          {subtitle && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
              {subtitle}
            </Typography>
          )}
        </Box>
        {actions && (
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            {actions}
          </Stack>
        )}
      </Stack>
      {children}
    </Box>
  );
}
