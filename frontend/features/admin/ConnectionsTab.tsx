"use client";
import NetworkCheckIcon from "@mui/icons-material/NetworkCheck";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import { Alert, Box, Button, Grid, Paper, Stack, Typography } from "@mui/material";
import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Section } from "@/components/common/Section";
import { StatusChip } from "@/components/common/StatusChip";
import { api } from "@/lib/api";
import { dateTime, titleCase } from "@/lib/format";
import { useApi } from "@/services/queries";
import DataTable from "@/tables/DataTable";
import { surface } from "@/styles/tokens";
import { useAdminInvalidate } from "./hooks";
import type { Subscription } from "./SubscriptionsTab";
import { errorMessage, KeyValueList, useCan, useToast } from "./ui";

interface ConnectionsResponse {
  identity: { auth_mode: string; tenant_id: string | null; client_id: string | null; client_secret_configured: boolean; storage_account_url: string | null; export_source: string; note: string };
  subscriptions: Subscription[];
}
interface Discovered {
  available: boolean;
  reason?: string;
  subscriptions: { subscription_id: string; display_name: string; state: string; tenant_id: string; registered: boolean }[];
}

const STEP_LABEL: Record<string, string> = { auth: "Authentication", subscription: "Subscription access", cost_api: "Cost Management API", exports: "Cost exports", storage: "Export storage" };

export function ConnectionsTab() {
  const q = useApi<ConnectionsResponse>("/azure/connections");
  const canAdmin = useCan("admin");
  const toast = useToast();
  const invalidate = useAdminInvalidate();
  const [testing, setTesting] = useState<string | null>(null);
  const [discovered, setDiscovered] = useState<Discovered | null>(null);

  const test = async (ids?: string[]) => {
    setTesting(ids?.[0] ?? "all");
    try {
      const r = await api<{ results: { subscription_id: string; overall?: string }[] }>(ids ? `/azure/connections/${ids[0]}/test` : "/azure/connections/test", { method: "POST", body: ids ? undefined : {} });
      const failed = r.results.filter((x) => x.overall === "failed").length;
      toast(`Tested ${r.results.length} subscription(s)${failed ? ` · ${failed} failed` : ""}`, failed ? "info" : "success");
      invalidate();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setTesting(null);
    }
  };

  const columns = useMemo<ColumnDef<Subscription, unknown>[]>(
    () => [
      { accessorKey: "subscription_name", header: "Subscription", size: 220, enableHiding: false, cell: ({ row }) => <Box><Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{row.original.subscription_name}</Typography><Typography variant="caption" noWrap component="div">{row.original.subscription_id}</Typography></Box> },
      { accessorKey: "application_name", header: "Application", size: 115, cell: ({ getValue }) => (getValue() as string) ?? "—" },
      { accessorKey: "environment_name", header: "Environment", size: 120 },
      { accessorKey: "auth_status", header: "Auth", size: 115, meta: { label: "Authentication" }, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
      { accessorKey: "cost_api_status", header: "Cost API", size: 125, meta: { label: "Cost API access" }, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
      { accessorKey: "storage_status", header: "Storage", size: 120, meta: { label: "Export / storage access" }, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
      { accessorKey: "connection_status", header: "Overall", size: 120, cell: ({ getValue }) => <StatusChip value={getValue() as string} /> },
      { accessorKey: "last_successful_sync_at", header: "Last collection", size: 175, meta: { label: "Last successful collection" }, cell: ({ getValue }) => dateTime(getValue() as string | null) },
      { accessorKey: "last_connection_test_at", header: "Last connection test", size: 180, cell: ({ getValue }) => dateTime(getValue() as string | null) },
      {
        id: "actions",
        header: "",
        size: 100,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) =>
          canAdmin ? (
            <Button size="small" disabled={!!testing} onClick={(e) => { e.stopPropagation(); test([row.original.subscription_id]); }} data-testid={`connection-test-${row.original.subscription_id}`}>
              {testing === row.original.subscription_id ? "Testing…" : "Test"}
            </Button>
          ) : null,
      },
    ],
    [canAdmin, testing], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const id = q.data?.identity;
  return (
    <Stack spacing={2} data-testid="connections-tab">
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Paper variant="outlined" sx={{ p: 2, height: "100%" }} data-testid="identity-panel">
            <Typography variant="h3" sx={{ mb: 1 }}>
              Collection identity (existing service principal)
            </Typography>
            {id ? (
              <KeyValueList
                data={{
                  auth_mode: id.auth_mode === "disabled" ? "Disabled (demo / local data only)" : id.auth_mode,
                  tenant_id: id.tenant_id,
                  client_id: id.client_id,
                  client_secret: id.client_secret_configured ? "Configured (never displayed)" : "Not configured",
                  storage_account_url: id.storage_account_url,
                  export_source: id.export_source === "local" ? "Local directory" : "Azure Blob Storage",
                }}
              />
            ) : (
              <Typography variant="caption">Loading…</Typography>
            )}
            <Typography variant="caption" component="div" sx={{ mt: 1 }}>
              {id?.note}
            </Typography>
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
            <Typography variant="h3" sx={{ mb: 1 }}>
              Required permissions (least privilege)
            </Typography>
            <Typography variant="body2" component="div">
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                <li><b>Cost Management Reader</b> on each subscription (cost query / exports read).</li>
                <li><b>Storage Blob Data Reader</b> on the export storage account or container.</li>
                <li>Optional: <b>Reader</b> for Azure Advisor recommendations and Activity Log evidence.</li>
                <li>Owner or Contributor is <b>never</b> required.</li>
              </ul>
            </Typography>
          </Paper>
        </Grid>
      </Grid>
      {id?.auth_mode === "disabled" && (
        <Alert severity="info" variant="outlined" sx={{ bgcolor: "#fff" }}>
          Azure integration is disabled (AZURE_AUTH_MODE=disabled). Tests report <i>not configured</i> for real subscriptions and <i>demo</i> for demo subscriptions, whose data comes from generated export files.
        </Alert>
      )}
      <Section
        title="Subscription connections"
        subtitle="Each subscription is validated independently against the real APIs — a failure in one never stops the others. Expand a row for step details and remediation."
        noPadding
        testId="connections-section"
        actions={
          canAdmin ? (
            <Stack direction="row" spacing={1}>
              <Button
                variant="outlined"
                color="inherit"
                startIcon={<TravelExploreIcon fontSize="small" />}
                onClick={async () => {
                  try {
                    setDiscovered(await api<Discovered>("/azure/subscriptions/discover"));
                  } catch (e) {
                    toast(errorMessage(e), "error");
                  }
                }}
                data-testid="discover-subscriptions"
              >
                Discover subscriptions
              </Button>
              <Button variant="contained" startIcon={<NetworkCheckIcon fontSize="small" />} disabled={!!testing} onClick={() => test()} data-testid="connections-test-all">
                {testing === "all" ? "Testing…" : "Test all connections"}
              </Button>
            </Stack>
          ) : undefined
        }
      >
        <DataTable
          data={q.data?.subscriptions ?? []}
          columns={columns}
          loading={q.isFetching}
          error={q.error ? errorMessage(q.error) : null}
          getRowId={(r) => r.subscription_id}
          storageKey="admin-connections"
          defaultHidden={["last_connection_test_at"]}
          testId="connections-table"
          renderSubRow={(s) => {
            const steps = s.connection_details?.steps;
            if (!steps) return <Typography variant="caption">Not tested yet. Use Test to validate access.</Typography>;
            return (
              <Grid container spacing={1.5}>
                {Object.entries(steps).map(([k, st]) => (
                  <Grid key={k} size={{ xs: 12, md: 6, xl: 4 }}>
                    <Box sx={{ p: 1.25, border: `1px solid ${surface.border}`, borderRadius: 1, bgcolor: "#fff", height: "100%" }}>
                      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
                        <Typography variant="subtitle1" sx={{ flex: 1 }}>
                          {STEP_LABEL[k] ?? titleCase(k)}
                        </Typography>
                        <StatusChip value={st.status} />
                      </Stack>
                      <Typography variant="body2" sx={{ wordBreak: "break-word" }}>
                        {st.message}
                      </Typography>
                      {st.remediation && (
                        <Typography variant="caption" component="div" sx={{ mt: 0.5, color: "#7a5200" }}>
                          Remediation: {st.remediation}
                        </Typography>
                      )}
                    </Box>
                  </Grid>
                ))}
                <Grid size={{ xs: 12 }}>
                  <Typography variant="caption">Tested {dateTime(s.connection_details?.tested_at ?? s.last_connection_test_at)}</Typography>
                </Grid>
              </Grid>
            );
          }}
        />
      </Section>
      {discovered && (
        <Section title="Subscriptions visible to the service principal" testId="discovered-section" noPadding>
          {!discovered.available ? (
            <Alert severity="info" sx={{ m: 1.5 }}>
              {discovered.reason}
            </Alert>
          ) : (
            <DataTable
              data={discovered.subscriptions}
              columns={[
                { accessorKey: "display_name", header: "Name", size: 260 },
                { accessorKey: "subscription_id", header: "Subscription ID", size: 300 },
                { accessorKey: "state", header: "State", size: 110 },
                { accessorKey: "tenant_id", header: "Tenant", size: 300 },
                { accessorKey: "registered", header: "Registered", size: 120, cell: ({ getValue }) => (getValue() ? <StatusChip value="ok" label="Registered" /> : <StatusChip value="untested" label="Not registered" />) },
              ]}
              storageKey="admin-discovered"
            />
          )}
        </Section>
      )}
    </Stack>
  );
}
