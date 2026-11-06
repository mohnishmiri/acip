"use client";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
import RefreshIcon from "@mui/icons-material/Refresh";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import {
  Avatar,
  Badge,
  Box,
  Button,
  Divider,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Popover,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { StatusChip } from "@/components/common/StatusChip";
import { useLinkWithFilters } from "@/hooks/useGlobalFilters";
import { api } from "@/lib/api";
import { DEV_ROLE_KEY, getDevRole } from "@/lib/auth";
import { dateTime, longDate } from "@/lib/format";
import { useApi, useFreshness, useMe } from "@/services/queries";
import { brand, surface } from "@/styles/tokens";
import { useAuth } from "./AuthProvider";
import { GlobalFilterBar } from "./GlobalFilters";
import { NAV, findNav } from "./nav";

const NAV_W = 248;
const NAV_W_COLLAPSED = 60;

function Logo({ collapsed }: { collapsed: boolean }) {
  return (
    <Stack direction="row" alignItems="center" spacing={1.25} sx={{ px: collapsed ? 1.5 : 2, height: 56, color: "#fff" }}>
      <Box sx={{ width: 30, height: 30, borderRadius: 1, bgcolor: brand.primary, display: "grid", placeItems: "center", flexShrink: 0 }} aria-hidden>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M4 18V11M10 18V6M16 18v-4M20 18H3" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      </Box>
      {!collapsed && (
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontWeight: 700, fontSize: 14, lineHeight: 1.1 }}>ACIP</Typography>
          <Typography sx={{ fontSize: 10.5, color: "rgba(255,255,255,0.65)", lineHeight: 1.2 }} noWrap>
            Azure Cost Intelligence
          </Typography>
        </Box>
      )}
    </Stack>
  );
}

function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const pathname = usePathname();
  const link = useLinkWithFilters();
  const current = findNav(pathname);
  return (
    <Box sx={{ width: collapsed ? NAV_W_COLLAPSED : NAV_W, flexShrink: 0, bgcolor: brand.nav, transition: "width .15s" }}>
    <Box component="nav" aria-label="Main navigation" sx={{ width: "100%", color: "#cfd6de", display: "flex", flexDirection: "column", position: "sticky", top: 0, height: "100vh", overflowY: "auto", overflowX: "hidden" }}>
      <Logo collapsed={collapsed} />
      <Box sx={{ flex: 1, py: 0.5 }}>
        {NAV.map((sec) => (
          <Box key={sec.section} sx={{ mb: 1 }}>
            {!collapsed && (
              <Typography variant="overline" sx={{ px: 2.25, color: "rgba(255,255,255,0.45)", display: "block", mt: 1 }}>
                {sec.section}
              </Typography>
            )}
            {collapsed && <Divider sx={{ borderColor: "rgba(255,255,255,0.08)", my: 1, mx: 1.5 }} />}
            <List dense disablePadding>
              {sec.items.map((item) => {
                const active = current?.href === item.href;
                const Icon = item.icon;
                const btn = (
                  <ListItemButton
                    component={Link}
                    href={link(item.href)}
                    selected={active}
                    data-testid={`nav-${item.href === "/" ? "overview" : item.href.slice(1)}`}
                    sx={{
                      mx: 1,
                      my: 0.25,
                      borderRadius: 1,
                      minHeight: 34,
                      px: collapsed ? 1.25 : 1.25,
                      color: active ? "#fff" : "#cfd6de",
                      "&.Mui-selected": { bgcolor: "rgba(15,108,189,0.35)", "&:hover": { bgcolor: "rgba(15,108,189,0.45)" } },
                      "&:hover": { bgcolor: "rgba(255,255,255,0.06)" },
                      borderLeft: active ? `3px solid ${brand.primary}` : "3px solid transparent",
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: collapsed ? 0 : 32, color: "inherit" }}>
                      <Icon sx={{ fontSize: 19 }} />
                    </ListItemIcon>
                    {!collapsed && <ListItemText primary={item.label} slotProps={{ primary: { sx: { fontSize: 12.75, fontWeight: active ? 600 : 500 }, noWrap: true } }} />}
                  </ListItemButton>
                );
                return collapsed ? (
                  <Tooltip key={item.href} title={item.label} placement="right">
                    {btn}
                  </Tooltip>
                ) : (
                  <Box key={item.href}>{btn}</Box>
                );
              })}
            </List>
          </Box>
        ))}
      </Box>
      <Box sx={{ p: 1, borderTop: "1px solid rgba(255,255,255,0.08)" }}>
        <Button fullWidth size="small" onClick={onToggle} sx={{ color: "#cfd6de", justifyContent: collapsed ? "center" : "flex-start", minWidth: 0 }} startIcon={collapsed ? undefined : <ChevronLeftIcon />} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}>
          {collapsed ? <ChevronRightIcon /> : "Collapse"}
        </Button>
      </Box>
    </Box>
    </Box>
  );
}

function FreshnessIndicator() {
  const { data } = useFreshness();
  if (!data) return null;
  const tip = (
    <Box sx={{ p: 0.5 }}>
      <div>Status: {data.status_label}</div>
      <div>Complete through: {longDate(data.complete_through ?? data.latest_usage_date)}</div>
      {data.complete_through && data.latest_usage_date && data.complete_through < data.latest_usage_date && (
        <div>Latest usage date: {longDate(data.latest_usage_date)} (partial — Azure is still billing it)</div>
      )}
      {data.oldest_latest_usage_date && data.oldest_latest_usage_date !== data.latest_usage_date && <div>Oldest subscription data: {longDate(data.oldest_latest_usage_date)}</div>}
      <div>Last successful ingestion: {dateTime(data.last_successful_ingestion)}</div>
      <div>Last ingestion attempt: {dateTime(data.last_ingestion_attempt)}</div>
      <div>
        Coverage: {data.subscriptions_with_data} of {data.subscriptions_enabled} subscriptions
      </div>
      <div style={{ marginTop: 4, opacity: 0.8 }}>{data.current_period_note}</div>
    </Box>
  );
  return (
    <Tooltip title={tip}>
      <Stack direction="row" spacing={1} alignItems="center" data-testid="freshness">
        <StatusChip value={data.status} label={data.status_label} />
        <Typography variant="caption" sx={{ display: { xs: "none", lg: "block" } }}>
          Data through <b>{longDate(data.complete_through ?? data.latest_usage_date)}</b> (UTC)
          {data.complete_through && data.latest_usage_date && data.complete_through < data.latest_usage_date ? ` · ${longDate(data.latest_usage_date).slice(0, 6)} updating` : ""}
        </Typography>
      </Stack>
    </Tooltip>
  );
}

function Notifications() {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const link = useLinkWithFilters();
  const qc = useQueryClient();
  const { data, refetch } = useApi<{ data: { id: number; title: string; message: string; severity: string; link: string | null; is_read: boolean; created_at: string; type: string }[]; meta: { unread: number } }>(
    "/notifications",
    { page_size: 8 },
    { refetchInterval: 120_000 },
  );
  const unread = data?.meta.unread ?? 0;
  return (
    <>
      <Tooltip title="Notifications">
        <IconButton onClick={(e) => setAnchor(e.currentTarget)} aria-label={`Notifications (${unread} unread)`} data-testid="notifications">
          <Badge badgeContent={unread} color="error" max={99}>
            <NotificationsNoneOutlinedIcon />
          </Badge>
        </IconButton>
      </Tooltip>
      <Popover anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }} slotProps={{ paper: { sx: { width: 380 } } }}>
        <Stack direction="row" alignItems="center" sx={{ px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}` }}>
          <Typography variant="h3" sx={{ flex: 1 }}>
            Notifications
          </Typography>
          <Button
            size="small"
            onClick={async () => {
              await api("/notifications/read", { method: "POST", body: {} });
              await refetch();
              qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "/notifications" });
            }}
          >
            Mark all read
          </Button>
        </Stack>
        <Box sx={{ maxHeight: 420, overflowY: "auto" }}>
          {data?.data.length ? (
            data.data.map((n) => (
              <Box key={n.id} component={Link} href={n.link ? link(n.link) : link("/alerts")} onClick={() => setAnchor(null)} sx={{ display: "block", px: 2, py: 1.25, borderBottom: `1px solid ${surface.border}`, textDecoration: "none", color: "inherit", bgcolor: n.is_read ? "transparent" : "#f5f9fe", "&:hover": { bgcolor: surface.hover } }}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <StatusChip value={n.severity} label={n.severity} tone={n.severity === "critical" ? "critical" : n.severity === "high" ? "serious" : n.severity === "medium" ? "warning" : "info"} />
                  <Typography variant="caption">{dateTime(n.created_at)}</Typography>
                </Stack>
                <Typography variant="body2" sx={{ fontWeight: 600, mt: 0.5 }}>
                  {n.title}
                </Typography>
                <Typography variant="caption" component="div" sx={{ color: "text.secondary" }}>
                  {n.message}
                </Typography>
              </Box>
            ))
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
              No notifications.
            </Typography>
          )}
        </Box>
        <Box sx={{ p: 1, textAlign: "center" }}>
          <Button component={Link} href={link("/alerts")} onClick={() => setAnchor(null)} size="small">
            View all alerts
          </Button>
        </Box>
      </Popover>
    </>
  );
}

function UserMenu() {
  const { data: me } = useMe();
  const auth = useAuth();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [devRole, setDevRole] = useState<string | null>(null);
  const qc = useQueryClient();
  useEffect(() => setDevRole(getDevRole()), []);
  const initials = (me?.name ?? "?").split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase();
  const roles = ["administrator", "finops_analyst", "engineering_lead", "viewer"];
  return (
    <>
      <IconButton onClick={(e) => setAnchor(e.currentTarget)} aria-label="User menu" data-testid="user-menu">
        <Avatar sx={{ width: 30, height: 30, fontSize: 12.5, bgcolor: brand.primary }}>{initials}</Avatar>
      </IconButton>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)} slotProps={{ paper: { sx: { minWidth: 260 } } }}>
        <Box sx={{ px: 2, py: 1 }}>
          <Typography variant="subtitle1">{me?.name}</Typography>
          <Typography variant="caption" component="div">
            {me?.email ?? (me?.auth_mode === "disabled" ? "Local development (authentication disabled)" : "")}
          </Typography>
          <Typography variant="caption" component="div">
            Role: <b>{me?.primary_role?.replace(/_/g, " ")}</b>
          </Typography>
        </Box>
        {me?.auth_mode === "disabled" && [
          <Divider key="d" />,
          <Typography key="t" variant="overline" sx={{ px: 2, color: "text.secondary" }}>
            Simulate role (local only)
          </Typography>,
          ...roles.map((r) => (
            <MenuItem
              key={r}
              selected={(devRole ?? "administrator") === r}
              onClick={() => {
                if (r === "administrator") window.localStorage.removeItem(DEV_ROLE_KEY);
                else window.localStorage.setItem(DEV_ROLE_KEY, r);
                setDevRole(r);
                setAnchor(null);
                qc.invalidateQueries();
              }}
            >
              {r.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </MenuItem>
          )),
        ]}
        {auth.mode === "entra" && [
          <Divider key="d2" />,
          <MenuItem key="so" onClick={() => auth.signOut()}>
            Sign out
          </MenuItem>,
        ]}
      </Menu>
    </>
  );
}

function DemoBanner() {
  const { data } = useFreshness();
  if (!data?.is_demo) return null;
  return (
    <Box role="note" sx={{ bgcolor: "#f3effc", color: "#4b2a8a", borderBottom: "1px solid #d6c9f2", px: 2.5, py: 0.5, display: "flex", alignItems: "center", gap: 1, fontSize: 12 }} data-testid="demo-banner">
      <ScienceOutlinedIcon sx={{ fontSize: 16 }} />
      <b>DEMO DATA</b>
      <span>— all figures are synthetic and generated for demonstration. They do not represent actual Azure billing.</span>
    </Box>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const nav = findNav(pathname);
  const qc = useQueryClient();
  const router = useRouter();
  useEffect(() => {
    setCollapsed(window.localStorage.getItem("acip.navCollapsed") === "1");
  }, []);
  const toggle = () => {
    setCollapsed((c) => {
      window.localStorage.setItem("acip.navCollapsed", c ? "0" : "1");
      return !c;
    });
  };
  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar collapsed={collapsed} onToggle={toggle} />
      <Box sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <DemoBanner />
        <Box component="header" sx={{ position: "sticky", top: 0, zIndex: 10, bgcolor: "#fff", borderBottom: `1px solid ${surface.border}` }}>
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ px: 2.5, height: 52 }}>
            <Typography variant="h2" noWrap sx={{ flex: 1 }} data-testid="page-title">
              {nav?.label ?? "ACIP"}
            </Typography>
            <FreshnessIndicator />
            <Tooltip title="Reload results from the database (does not call Azure)">
              <Button
                variant="outlined"
                color="inherit"
                size="small"
                startIcon={<RefreshIcon fontSize="small" />}
                onClick={() => {
                  qc.invalidateQueries();
                  router.refresh();
                }}
                sx={{ borderColor: "divider" }}
                data-testid="refresh"
              >
                Refresh
              </Button>
            </Tooltip>
            <Notifications />
            <UserMenu />
          </Stack>
          {!nav?.inlineFilters && (
            <Box sx={{ px: 2.5, py: 1, borderTop: `1px solid ${surface.border}`, bgcolor: surface.subtle }}>
              <GlobalFilterBar dateRange={nav?.dateRange ?? false} />
            </Box>
          )}
        </Box>
        <Box component="main" sx={{ flex: 1, p: 2.5, minWidth: 0 }}>
          {children}
        </Box>
      </Box>
    </Box>
  );
}
