"use client";
import { Alert, Box, Tab, Tabs } from "@mui/material";
import { PageHeader } from "@/components/common/PageHeader";
import { useUrlState } from "@/hooks/useUrlState";
import { useMe } from "@/services/queries";
import { AllocationTab } from "./AllocationTab";
import { AnomalyRulesTab } from "./AnomalyRulesTab";
import { ApplicationsTab } from "./ApplicationsTab";
import { AuditTab } from "./AuditTab";
import { CategoriesTab } from "./CategoriesTab";
import { ConnectionsTab } from "./ConnectionsTab";
import { SettingsTab } from "./SettingsTab";
import { SubscriptionsTab } from "./SubscriptionsTab";
import { UsersTab } from "./UsersTab";
import { ToastProvider } from "./ui";

const TABS = [
  { value: "subscriptions", label: "Subscriptions" },
  { value: "connections", label: "Azure Connections" },
  { value: "applications", label: "Applications" },
  { value: "allocation", label: "Allocation rules" },
  { value: "categories", label: "Service categories" },
  { value: "anomaly-rules", label: "Anomaly rules" },
  { value: "settings", label: "Settings" },
  { value: "users", label: "Users & roles" },
  { value: "audit", label: "Audit log" },
];

export default function AdminPage() {
  const [s, set] = useUrlState({ tab: "subscriptions" });
  const { data: me } = useMe();
  const isAdmin = !!me?.permissions.includes("admin");
  return (
    <ToastProvider>
      <Box data-testid="admin-page">
        <PageHeader title="Administration & Settings" subtitle="Subscriptions, Azure connections, allocation rules, detection thresholds, runtime settings and access control. Changes are audited." />
        {me && !isAdmin && (
          <Alert severity="info" variant="outlined" sx={{ mb: 2, bgcolor: "#fff" }}>
            You are signed in as <b>{me.primary_role?.replace(/_/g, " ")}</b>. Configuration is read-only for your role; changes require the Administrator role.
          </Alert>
        )}
        <Tabs value={s.tab} onChange={(_, v) => set({ tab: v })} variant="scrollable" scrollButtons="auto" sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
          {TABS.map((t) => (
            <Tab key={t.value} value={t.value} label={t.label} data-testid={`admin-tab-${t.value}`} />
          ))}
        </Tabs>
        {s.tab === "subscriptions" && <SubscriptionsTab />}
        {s.tab === "connections" && <ConnectionsTab />}
        {s.tab === "applications" && <ApplicationsTab />}
        {s.tab === "allocation" && <AllocationTab />}
        {s.tab === "categories" && <CategoriesTab />}
        {s.tab === "anomaly-rules" && <AnomalyRulesTab />}
        {s.tab === "settings" && <SettingsTab />}
        {s.tab === "users" && <UsersTab />}
        {s.tab === "audit" && <AuditTab />}
      </Box>
    </ToastProvider>
  );
}
