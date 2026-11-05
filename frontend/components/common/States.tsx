"use client";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import InboxOutlinedIcon from "@mui/icons-material/InboxOutlined";
import { Alert, Box, Button, Skeleton, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";
import { ApiError } from "@/lib/api";

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : "Something went wrong.";
  const rid = error instanceof ApiError ? error.requestId : null;
  const forbidden = error instanceof ApiError && error.status === 403;
  return (
    <Stack alignItems="center" spacing={1} sx={{ py: 5, px: 2, textAlign: "center" }} role="alert">
      <ErrorOutlineIcon color={forbidden ? "warning" : "error"} />
      <Typography variant="subtitle1">{forbidden ? "You don't have access to this view" : "Unable to load data"}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 520 }}>
        {msg}
      </Typography>
      {rid && <Typography variant="caption">Request id: {rid}</Typography>}
      {onRetry && !forbidden && (
        <Button size="small" variant="outlined" onClick={onRetry}>
          Retry
        </Button>
      )}
    </Stack>
  );
}

export function EmptyState({ title = "No data", message, action }: { title?: string; message?: ReactNode; action?: ReactNode }) {
  return (
    <Stack alignItems="center" spacing={1} sx={{ py: 5, px: 2, textAlign: "center" }}>
      <InboxOutlinedIcon sx={{ color: "text.disabled" }} />
      <Typography variant="subtitle1">{title}</Typography>
      {message && (
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 520 }}>
          {message}
        </Typography>
      )}
      {action}
    </Stack>
  );
}

export function ChartSkeleton({ height = 300 }: { height?: number }) {
  return (
    <Box sx={{ height, display: "flex", alignItems: "flex-end", gap: 1, px: 1, pb: 1 }} aria-busy="true" aria-label="Loading chart">
      {[40, 65, 50, 80, 55, 70, 45, 85, 60, 75].map((h, i) => (
        <Skeleton key={i} variant="rectangular" sx={{ flex: 1, height: `${h}%`, borderRadius: "4px 4px 0 0" }} />
      ))}
    </Box>
  );
}

export function Warnings({ warnings }: { warnings?: string[] }) {
  if (!warnings?.length) return null;
  return (
    <Stack spacing={0.75}>
      {warnings.map((w) => (
        <Alert key={w} severity="info" variant="outlined" sx={{ bgcolor: "#fff" }}>
          {w}
        </Alert>
      ))}
    </Stack>
  );
}
