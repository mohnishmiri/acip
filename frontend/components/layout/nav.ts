import AccountBalanceWalletOutlinedIcon from "@mui/icons-material/AccountBalanceWalletOutlined";
import AppsOutlinedIcon from "@mui/icons-material/AppsOutlined";
import CloudSyncOutlinedIcon from "@mui/icons-material/CloudSyncOutlined";
import CompareArrowsOutlinedIcon from "@mui/icons-material/CompareArrowsOutlined";
import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import Inventory2OutlinedIcon from "@mui/icons-material/Inventory2Outlined";
import LayersOutlinedIcon from "@mui/icons-material/LayersOutlined";
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
import QueryStatsOutlinedIcon from "@mui/icons-material/QueryStatsOutlined";
import ReportGmailerrorredOutlinedIcon from "@mui/icons-material/ReportGmailerrorredOutlined";
import SavingsOutlinedIcon from "@mui/icons-material/SavingsOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import TroubleshootOutlinedIcon from "@mui/icons-material/TroubleshootOutlined";
import type { SvgIconComponent } from "@mui/icons-material";

export interface NavItem {
  label: string;
  href: string;
  icon: SvgIconComponent;
  dateRange?: boolean; // whether the global date range applies on this page
  inlineFilters?: boolean; // page renders the global filters in its own toolbar
}

export const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Analyze",
    items: [
      { label: "Executive Overview", href: "/", icon: DashboardOutlinedIcon, dateRange: true },
      { label: "Cost Explorer", href: "/explorer", icon: QueryStatsOutlinedIcon, dateRange: true, inlineFilters: true },
      { label: "Cost Comparison", href: "/comparison", icon: CompareArrowsOutlinedIcon, dateRange: true },
      { label: "Cost Anomalies", href: "/anomalies", icon: ReportGmailerrorredOutlinedIcon },
      { label: "Resource Analysis", href: "/resources", icon: Inventory2OutlinedIcon, dateRange: true },
      { label: "Cost Investigation", href: "/investigation", icon: TroubleshootOutlinedIcon, dateRange: true },
    ],
  },
  {
    section: "Allocate & Plan",
    items: [
      { label: "Application Cost Allocation", href: "/applications", icon: AppsOutlinedIcon, dateRange: true },
      { label: "Production vs Non-Production", href: "/environments", icon: LayersOutlinedIcon, dateRange: true },
      { label: "Budget & Forecast", href: "/budgets", icon: AccountBalanceWalletOutlinedIcon },
      { label: "Potential Cost Savings", href: "/savings", icon: SavingsOutlinedIcon },
    ],
  },
  {
    section: "Operate",
    items: [
      { label: "Alerts & Notifications", href: "/alerts", icon: NotificationsNoneOutlinedIcon },
      { label: "Data Management", href: "/data-management", icon: CloudSyncOutlinedIcon },
      { label: "Administration & Settings", href: "/admin", icon: SettingsOutlinedIcon },
    ],
  },
];

export function findNav(pathname: string): NavItem | undefined {
  const all = NAV.flatMap((s) => s.items);
  return all.find((i) => (i.href === "/" ? pathname === "/" : pathname === i.href || pathname.startsWith(`${i.href}/`)));
}
