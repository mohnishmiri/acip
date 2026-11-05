"use client";
import { Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Section } from "@/components/common/Section";
import { dateTime } from "@/lib/format";
import { useApi } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { errorMessage, KeyValueList, useCan } from "./ui";

interface Entry {
  id: number;
  actor: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export function AuditTab() {
  const canAdmin = useCan("admin");
  const [paging, setPaging] = useState({ page: 1, size: 50 });
  const q = useApi<{ data: Entry[]; meta: { total: number } }>(canAdmin ? "/admin/audit-logs" : null, { page: paging.page, page_size: paging.size });
  const cols = useMemo<ColumnDef<Entry, unknown>[]>(
    () => [
      { accessorKey: "created_at", header: "When", size: 180, cell: ({ getValue }) => dateTime(getValue() as string) },
      { accessorKey: "actor", header: "Actor", size: 200 },
      { accessorKey: "action", header: "Action", size: 200, cell: ({ getValue }) => <Typography variant="body2" sx={{ fontFamily: "monospace" }}>{getValue() as string}</Typography> },
      { accessorKey: "entity_type", header: "Entity", size: 150, cell: ({ getValue }) => (getValue() as string) ?? "—" },
      { accessorKey: "entity_id", header: "Entity id", size: 280, cell: ({ getValue }) => <Typography variant="caption" noWrap component="div">{(getValue() as string) ?? "—"}</Typography> },
      { id: "details", header: "Details", size: 360, accessorFn: (r) => JSON.stringify(r.details ?? {}), cell: ({ getValue }) => <Typography variant="caption" noWrap component="div" title={getValue() as string}>{getValue() as string}</Typography> },
      { accessorKey: "ip_address", header: "IP", size: 120, cell: ({ getValue }) => (getValue() as string) ?? "—" },
    ],
    [],
  );
  if (!canAdmin) return <Typography variant="body2">The audit log is available to administrators.</Typography>;
  return (
    <Section title="Audit log" subtitle="Configuration changes, ingestion triggers, status changes and budget edits." noPadding testId="audit-section">
      <DataTable
        data={q.data?.data ?? []}
        columns={cols}
        loading={q.isFetching}
        error={q.error ? errorMessage(q.error) : null}
        getRowId={(r) => String(r.id)}
        serverPaging={{ page: paging.page, pageSize: paging.size, total: q.data?.meta.total ?? 0, onChange: (page, size) => setPaging({ page, size }) }}
        storageKey="admin-audit"
        defaultHidden={["ip_address"]}
        emptyMessage="No audit entries yet."
        testId="audit-table"
        renderSubRow={(r) => <KeyValueList data={r.details ?? {}} />}
      />
    </Section>
  );
}
