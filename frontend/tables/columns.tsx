"use client";
import { Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import { DeltaText, MoneyText } from "@/components/common/Delta";
import { StatusChip } from "@/components/common/StatusChip";
import { num, pct } from "@/lib/format";
import type { GroupItem } from "@/lib/types";

/** Standard comparison columns shared by explorer, comparison and drill-down tables. */
export function comparisonColumns(opts: { currency: string; hasComparison: boolean; labelHeader: string; onLabelClick?: (g: GroupItem) => void }): ColumnDef<GroupItem, unknown>[] {
  const cols: ColumnDef<GroupItem, unknown>[] = [
    {
      id: "label",
      accessorKey: "label",
      header: opts.labelHeader,
      size: 280,
      enableHiding: false,
      cell: ({ row }) => (
        <Typography variant="body2" noWrap title={row.original.key} sx={{ fontWeight: 600, color: opts.onLabelClick && row.original.key !== "__other__" ? "primary.main" : "inherit" }}>
          {row.original.label}
        </Typography>
      ),
    },
  ];
  if (opts.hasComparison) {
    cols.push({ id: "previous", accessorKey: "previous", header: "Previous", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={opts.currency} /> });
  }
  cols.push({ id: "current", accessorKey: "current", header: "Current", size: 130, meta: { numeric: true }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={opts.currency} bold /> });
  if (opts.hasComparison) {
    cols.push(
      { id: "diff", accessorKey: "diff", header: "Difference", size: 130, meta: { numeric: true }, cell: ({ row }) => <DeltaText value={row.original.diff} currency={opts.currency} /> },
      { id: "pct", accessorKey: "pct", header: "Change %", size: 100, meta: { numeric: true }, sortUndefined: "last", cell: ({ row }) => <DeltaText value={row.original.pct} kind="pct" status={row.original.status} /> },
      { id: "status", accessorKey: "status", header: "Status", size: 110, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
      { id: "contribution_pct", accessorKey: "contribution_pct", header: "Contribution", size: 125, meta: { numeric: true, label: "Contribution to change" }, cell: ({ getValue }) => pct(getValue() as number | null) },
    );
  }
  cols.push(
    { id: "share_of_total", accessorKey: "share_of_total", header: "Share", size: 90, meta: { numeric: true, label: "Share of total" }, cell: ({ getValue }) => pct(getValue() as number | null, { sign: false }) },
    { id: "current_daily_avg", accessorKey: "current_daily_avg", header: "Daily avg", size: 110, meta: { numeric: true, label: "Current daily average" }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={opts.currency} /> },
  );
  if (opts.hasComparison) {
    cols.push({ id: "previous_daily_avg", accessorKey: "previous_daily_avg", header: "Prev daily avg", size: 120, meta: { numeric: true, label: "Previous daily average" }, cell: ({ getValue }) => <MoneyText value={getValue() as number} currency={opts.currency} /> });
  }
  cols.push({ id: "current_records", accessorKey: "current_records", header: "Records", size: 90, meta: { numeric: true, label: "Billing records" }, cell: ({ getValue }) => num(getValue() as number, 0) });
  return cols;
}
