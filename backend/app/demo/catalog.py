"""DEMO DATA catalog: synthetic applications, subscriptions, resources and meters.

Every value produced from this catalog is synthetic and is labelled DEMO DATA in the
database (is_demo) and in the UI. Nothing here represents real Azure billing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

DEMO_TENANT = "00000000-0000-0000-0000-00000000de00"

APPLICATIONS = [
    ("app1", "Application 1", "Customer Portal (demo placeholder)", 10),
    ("app2", "Application 2", "Payments Platform (demo placeholder)", 20),
    ("app3", "Application 3", "Analytics & Reporting (demo placeholder)", 30),
]

# (index, application code, environment code, subscription guid, name, region)
SUBSCRIPTIONS = [
    (1, "app1", "production", "de000000-0000-4000-8000-000000000001", "DEMO-App1-Production", "eastus"),
    (2, "app1", "non_production", "de000000-0000-4000-8000-000000000002", "DEMO-App1-NonProduction", "eastus"),
    (3, "app2", "production", "de000000-0000-4000-8000-000000000003", "DEMO-App2-Production", "westeurope"),
    (4, "app2", "non_production", "de000000-0000-4000-8000-000000000004", "DEMO-App2-NonProduction", "westeurope"),
    (5, "app3", "production", "de000000-0000-4000-8000-000000000005", "DEMO-App3-Production", "eastus2"),
    (6, "app3", "non_production", "de000000-0000-4000-8000-000000000006", "DEMO-App3-NonProduction", "eastus2"),
]

# Mandatory demonstration scenario (weekly totals, actual cost, all subscriptions).
# "Other" in the scenario is the sum of the remaining service categories.
SCENARIO_PREVIOUS = {
    "Azure Kubernetes Service": Decimal("30000"),
    "Azure SQL": Decimal("20000"),
    "Storage": Decimal("10000"),
    "Networking": Decimal("8000"),
    "Virtual Machines": Decimal("12000"),
    "App Service": Decimal("8000"),
    "Azure Monitor": Decimal("7000"),
    "Key Vault": Decimal("1500"),
    "Container Registry": Decimal("2000"),
    "Other Services": Decimal("1500"),
}
SCENARIO_CURRENT = {
    "Azure Kubernetes Service": Decimal("34500"),
    "Azure SQL": Decimal("22000"),
    "Storage": Decimal("11500"),
    "Networking": Decimal("9000"),
    "Virtual Machines": Decimal("12300"),
    "App Service": Decimal("8250"),
    "Azure Monitor": Decimal("7350"),
    "Key Vault": Decimal("1520"),
    "Container Registry": Decimal("2030"),
    "Other Services": Decimal("1550"),
}


@dataclass(frozen=True)
class Meter:
    category: str
    subcategory: str
    name: str
    unit: str
    price: Decimal
    consumed_service: str
    product: str
    service_family: str
    service_type: str | None = None  # VM size (additionalInfo.ServiceType)

    @property
    def meter_id(self) -> str:
        import uuid

        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"acip-demo-meter/{self.category}/{self.subcategory}/{self.name}"))


def _vm(size: str, price: str, family: str = "Dsv5 Series") -> Meter:
    return Meter("Virtual Machines", family, size.replace("Standard_", "").replace("_", " "), "1 Hour", Decimal(price),
                 "Microsoft.Compute", f"Virtual Machines {family} - {size}", "Compute", size)


M = {
    "aks_sla": Meter("Azure Kubernetes Service", "Standard", "Standard Uptime SLA", "1 Hour", Decimal("0.10"), "Microsoft.ContainerService", "Azure Kubernetes Service - Standard", "Compute"),
    "d8s": _vm("Standard_D8s_v5", "0.384"),
    "e16s": _vm("Standard_E16s_v5", "1.008", "Esv5 Series"),
    "e8s": _vm("Standard_E8s_v5", "0.504", "Esv5 Series"),
    "d4s": _vm("Standard_D4s_v5", "0.192"),
    "d16s": _vm("Standard_D16s_v5", "0.768"),
    "b2ms": _vm("Standard_B2ms", "0.0832", "BS Series"),
    "nc6s": _vm("Standard_NC6s_v3", "3.06", "NCSv3 Series"),
    "p30": Meter("Storage", "Premium SSD Managed Disks", "P30 LRS Disk", "1/Month", Decimal("135.17"), "Microsoft.Compute", "Premium SSD Managed Disks - P30 - LRS", "Storage"),
    "lb": Meter("Load Balancer", "Standard", "Standard Data Processed", "1 GB", Decimal("0.005"), "Microsoft.Network", "Load Balancer - Standard", "Networking"),
    "sql_gp": Meter("SQL Database", "General Purpose - Compute Gen5", "vCore", "1 Hour", Decimal("0.5044"), "Microsoft.Sql", "SQL Database Single General Purpose - Compute Gen5", "Databases"),
    "sql_bc": Meter("SQL Database", "Business Critical - Compute Gen5", "vCore", "1 Hour", Decimal("1.3618"), "Microsoft.Sql", "SQL Database Single Business Critical - Compute Gen5", "Databases"),
    "sql_backup": Meter("SQL Database", "Single/Elastic Pool PITR Backup Storage", "LRS Data Stored", "1 GB/Month", Decimal("0.20"), "Microsoft.Sql", "SQL Database Single/Elastic Pool PITR Backup Storage", "Databases"),
    "sql_mi": Meter("SQL Managed Instance", "General Purpose - Compute Gen5", "vCore", "1 Hour", Decimal("0.5044"), "Microsoft.Sql", "SQL Managed Instance General Purpose - Compute Gen5", "Databases"),
    "blob_hot": Meter("Storage", "General Block Blob v2", "Hot LRS Data Stored", "1 GB/Month", Decimal("0.0208"), "Microsoft.Storage", "General Block Blob v2 Hierarchical Namespace", "Storage"),
    "blob_tx": Meter("Storage", "General Block Blob v2", "Hot Write Operations", "10K", Decimal("0.065"), "Microsoft.Storage", "General Block Blob v2", "Storage"),
    "egress": Meter("Bandwidth", "Rtn Preference: MGN", "Standard Data Transfer Out", "1 GB", Decimal("0.087"), "Microsoft.Network", "Rtn Preference: MGN - Standard Data Transfer Out", "Networking"),
    "pip": Meter("Virtual Network", "IP Addresses", "Standard IPv4 Static Public IP", "1 Hour", Decimal("0.005"), "Microsoft.Network", "IP Addresses - Standard IPv4 Static Public IP", "Networking"),
    "peering": Meter("Virtual Network", "Peering", "Intra-Region Ingress", "1 GB", Decimal("0.01"), "Microsoft.Network", "Virtual Network Peering - Intra-Region Ingress", "Networking"),
    "firewall": Meter("Azure Firewall", "Standard", "Standard Deployment", "1 Hour", Decimal("1.25"), "Microsoft.Network", "Azure Firewall - Standard", "Networking"),
    "agw": Meter("Application Gateway", "WAF v2", "Fixed Cost", "1 Hour", Decimal("0.443"), "Microsoft.Network", "Application Gateway WAF v2", "Networking"),
    "vpn": Meter("VPN Gateway", "VpnGw1", "VpnGw1", "1 Hour", Decimal("0.19"), "Microsoft.Network", "VPN Gateway VpnGw1", "Networking"),
    "asp": Meter("Azure App Service", "Premium v3 Plan", "P2 v3", "1 Hour", Decimal("0.40"), "Microsoft.Web", "Azure App Service Premium v3 Plan - P2 v3", "Compute"),
    "la_ingest": Meter("Log Analytics", "Analytics Logs", "Pay-as-you-go Data Ingestion", "1 GB", Decimal("2.76"), "Microsoft.OperationalInsights", "Log Analytics - Analytics Logs", "Management and Governance"),
    "appi": Meter("Application Insights", "Enterprise", "Data Ingestion", "1 GB", Decimal("2.30"), "microsoft.insights", "Application Insights", "Management and Governance"),
    "kv": Meter("Key Vault", "Premium", "Operations", "10K", Decimal("0.03"), "Microsoft.KeyVault", "Key Vault - Premium", "Security"),
    "acr": Meter("Container Registry", "Premium", "Premium Registry Unit", "1/Day", Decimal("1.667"), "Microsoft.ContainerRegistry", "Container Registry Premium", "Containers"),
    "acr_storage": Meter("Container Registry", "Premium", "Data Stored", "1 GB/Month", Decimal("0.10"), "Microsoft.ContainerRegistry", "Container Registry Premium", "Containers"),
    "backup": Meter("Backup", "Azure VM", "Protected Instances", "1/Month", Decimal("10.00"), "Microsoft.RecoveryServices", "Backup - Azure VM", "Management and Governance"),
    "defender": Meter("Microsoft Defender for Cloud", "Standard", "Standard Node", "1/Day", Decimal("0.50"), "Microsoft.Security", "Microsoft Defender for Servers", "Security"),
}


@dataclass
class Event:
    kind: str  # scale | ramp | spike | weekly_growth
    start: str  # relative day token, resolved by the generator
    end: str | None = None
    factor: float = 1.0


@dataclass
class Stream:
    sub: int
    name: str
    rg: str
    rtype: str
    meter: str
    category: str
    base: float  # average daily cost at the reference (previous scenario) week
    profile: str = "prod"
    tags: dict[str, str] = field(default_factory=dict)
    growth: float = 0.012  # monthly
    events: list[Event] = field(default_factory=list)
    active_from: str | None = None  # relative token
    active_to: str | None = None
    parent: str | None = None  # parent resource path for nested types (e.g. SQL server)
    reserved_from: date | None = None  # reservation covers usage from this date
    reserved_daily_amortized: float = 0.0


def T(app: str, env: str, owner: str, cc: str, workload: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    tags = {"application": app, "environment": env, "owner": owner, "cost-center": cc, "workload": workload, "demo": "true"}
    if extra:
        tags.update(extra)
    return tags


def _t1p(w: str) -> dict[str, str]:
    return T("app1", "prod", "portal-team@contoso.example", "CC-1001", w)


def _t1n(w: str) -> dict[str, str]:
    return T("app1", "dev", "portal-team@contoso.example", "CC-1001", w)


def _t2p(w: str) -> dict[str, str]:
    return T("app2", "prod", "payments-team@contoso.example", "CC-2002", w)


def _t2n(w: str) -> dict[str, str]:
    return T("app2", "test", "payments-team@contoso.example", "CC-2002", w)


def _t3p(w: str) -> dict[str, str]:
    return T("app3", "prod", "analytics-team@contoso.example", "CC-3003", w)


def _t3n(w: str) -> dict[str, str]:
    return T("app3", "dev", "analytics-team@contoso.example", "CC-3003", w)


VMSS = "Microsoft.Compute/virtualMachineScaleSets"
VM = "Microsoft.Compute/virtualMachines"
DISK = "Microsoft.Compute/disks"
AKS = "Microsoft.ContainerService/managedClusters"

STREAMS: list[Stream] = [
    # ---------------- Azure Kubernetes Service ----------------
    Stream(1, "aks-app1-prod", "rg-app1-prod-aks", AKS, "aks_sla", "Azure Kubernetes Service", 2.4, tags=_t1p("aks")),
    Stream(1, "aks-system-31415926-vmss", "MC_rg-app1-prod-aks_aks-app1-prod_eastus", VMSS, "d8s", "Azure Kubernetes Service", 280, tags={"aks-managed-cluster-name": "aks-app1-prod"}),
    Stream(1, "aks-userpool-27182818-vmss", "MC_rg-app1-prod-aks_aks-app1-prod_eastus", VMSS, "e16s", "Azure Kubernetes Service", 1600,
           tags={"aks-managed-cluster-name": "aks-app1-prod"}, events=[Event("scale", "cur+2", None, 1.45)]),
    Stream(1, "aks-app1-prod-osdisks", "MC_rg-app1-prod-aks_aks-app1-prod_eastus", DISK, "p30", "Azure Kubernetes Service", 120, tags={"aks-managed-cluster-name": "aks-app1-prod"}),
    Stream(1, "kubernetes", "MC_rg-app1-prod-aks_aks-app1-prod_eastus", "Microsoft.Network/loadBalancers", "lb", "Azure Kubernetes Service", 30),
    Stream(2, "aks-system-11235813-vmss", "MC_rg-app1-np-aks_aks-app1-np_eastus", VMSS, "d8s", "Azure Kubernetes Service", 90, "nonprod_247"),
    Stream(2, "aks-userpool-21345589-vmss", "MC_rg-app1-np-aks_aks-app1-np_eastus", VMSS, "e8s", "Azure Kubernetes Service", 260, "nonprod_247"),
    Stream(2, "aks-app1-np-osdisks", "MC_rg-app1-np-aks_aks-app1-np_eastus", DISK, "p30", "Azure Kubernetes Service", 30, "nonprod_247"),
    Stream(3, "aks-system-14142135-vmss", "MC_rg-app2-prod-aks_aks-app2-prod_westeurope", VMSS, "d8s", "Azure Kubernetes Service", 200),
    Stream(3, "aks-userpool-17320508-vmss", "MC_rg-app2-prod-aks_aks-app2-prod_westeurope", VMSS, "d16s", "Azure Kubernetes Service", 900),
    Stream(3, "aks-app2-prod-osdisks", "MC_rg-app2-prod-aks_aks-app2-prod_westeurope", DISK, "p30", "Azure Kubernetes Service", 60),
    Stream(4, "aks-userpool-22360679-vmss", "MC_rg-app2-np-aks_aks-app2-np_westeurope", VMSS, "d4s", "Azure Kubernetes Service", 180, "nonprod_office"),
    Stream(5, "aks-system-26457513-vmss", "MC_rg-app3-prod-aks_aks-app3-prod_eastus2", VMSS, "d8s", "Azure Kubernetes Service", 90),
    Stream(5, "aks-userpool-28284271-vmss", "MC_rg-app3-prod-aks_aks-app3-prod_eastus2", VMSS, "e8s", "Azure Kubernetes Service", 420, events=[Event("scale", "cur+0", None, 1.08)]),
    # ---------------- Azure SQL ----------------
    Stream(1, "sqldb-app1-prod-orders", "rg-app1-prod-data", "Microsoft.Sql/servers/databases", "sql_bc", "Azure SQL", 900, tags=_t1p("orders-db"), parent="sql-app1-prod"),
    Stream(1, "sqldb-app1-prod-orders", "rg-app1-prod-data", "Microsoft.Sql/servers/databases", "sql_backup", "Azure SQL", 40, "storage", tags=_t1p("orders-db"), parent="sql-app1-prod", growth=0.02),
    Stream(2, "sqldb-app1-dev", "rg-app1-np-data", "Microsoft.Sql/servers/databases", "sql_gp", "Azure SQL", 110, "nonprod_247", tags=_t1n("orders-db"), parent="sql-app1-np"),
    Stream(3, "sqldb-app2-prod-core", "rg-app2-prod-data", "Microsoft.Sql/servers/databases", "sql_gp", "Azure SQL", 780, tags=_t2p("ledger-db"), parent="sql-app2-prod"),
    # Tier change GP -> Business Critical on day 2 of the current week (meter swap)
    Stream(3, "sqldb-app2-prod-reporting", "rg-app2-prod-data", "Microsoft.Sql/servers/databases", "sql_gp", "Azure SQL", 120, tags=_t2p("reporting-db"), parent="sql-app2-prod", active_to="cur+0"),
    Stream(3, "sqldb-app2-prod-reporting", "rg-app2-prod-data", "Microsoft.Sql/servers/databases", "sql_bc", "Azure SQL", 324, tags=_t2p("reporting-db"), parent="sql-app2-prod", active_from="cur+1"),
    Stream(4, "sqldb-app2-test", "rg-app2-np-data", "Microsoft.Sql/servers/databases", "sql_gp", "Azure SQL", 90, "nonprod_247", tags=_t2n("ledger-db"), parent="sql-app2-np"),
    Stream(5, "sqlmi-app3-prod", "rg-app3-prod-data", "Microsoft.Sql/managedInstances", "sql_mi", "Azure SQL", 700, tags=_t3p("warehouse")),
    Stream(6, "sqldb-app3-dev", "rg-app3-np-data", "Microsoft.Sql/servers/databases", "sql_gp", "Azure SQL", 60, "nonprod_office", tags=_t3n("warehouse"), parent="sql-app3-np"),
    # ---------------- Storage ----------------
    Stream(1, "stapp1proddata", "rg-app1-prod-data", "Microsoft.Storage/storageAccounts", "blob_hot", "Storage", 520, "storage", tags=_t1p("data-lake"), growth=0.025,
           events=[Event("ramp", "cur+0", "cur+6", 1.30)]),
    Stream(1, "stapp1proddata", "rg-app1-prod-data", "Microsoft.Storage/storageAccounts", "blob_tx", "Storage", 60, "prod_business", tags=_t1p("data-lake")),
    Stream(2, "stapp1npdata", "rg-app1-np-data", "Microsoft.Storage/storageAccounts", "blob_hot", "Storage", 90, "storage", tags=_t1n("data-lake"), growth=0.0,
           events=[Event("weekly_growth", "prev-35", None, 1.06)]),
    Stream(3, "stapp2prod", "rg-app2-prod-data", "Microsoft.Storage/storageAccounts", "blob_hot", "Storage", 330, "storage", tags=_t2p("documents"), growth=0.02),
    Stream(4, "stapp2np", "rg-app2-np-data", "Microsoft.Storage/storageAccounts", "blob_hot", "Storage", 50, "storage", tags=_t2n("documents")),
    Stream(5, "stapp3prod", "rg-app3-prod-data", "Microsoft.Storage/storageAccounts", "blob_hot", "Storage", 260, "storage", tags=_t3p("warehouse"), growth=0.02),
    Stream(6, "stapp3np", "rg-app3-np-data", "Microsoft.Storage/storageAccounts", "blob_hot", "Storage", 60, "storage", tags=_t3n("warehouse")),
    # ---------------- Networking ----------------
    Stream(1, "vnet-hub-eastus", "rg-hub-network", "Microsoft.Network/virtualNetworks", "peering", "Networking", 60, tags={"owner": "platform-team@contoso.example", "cost-center": "CC-9000", "workload": "hub-network", "demo": "true"}),
    Stream(1, "afw-hub-eastus", "rg-hub-network", "Microsoft.Network/azureFirewalls", "firewall", "Networking", 310, tags={"owner": "platform-team@contoso.example", "cost-center": "CC-9000", "workload": "hub-network", "demo": "true"}),
    Stream(1, "pip-afw-hub-eastus", "rg-hub-network", "Microsoft.Network/publicIPAddresses", "egress", "Networking", 120, "prod_business", tags={"owner": "platform-team@contoso.example", "cost-center": "CC-9000", "workload": "hub-network", "demo": "true"}),
    Stream(1, "agw-app1-prod", "rg-app1-prod-web", "Microsoft.Network/applicationGateways", "agw", "Networking", 90, tags=_t1p("ingress")),
    Stream(3, "pip-app2-prod-ingress", "rg-app2-prod-web", "Microsoft.Network/publicIPAddresses", "egress", "Networking", 420, "prod_business", tags=_t2p("ingress"),
           events=[Event("scale", "cur+0", None, 1.30)]),
    Stream(3, "pip-app2-prod-ingress", "rg-app2-prod-web", "Microsoft.Network/publicIPAddresses", "pip", "Networking", 4, tags=_t2p("ingress")),
    Stream(4, "pip-app2-np-ingress", "rg-app2-np-web", "Microsoft.Network/publicIPAddresses", "egress", "Networking", 20, "nonprod_247", tags=_t2n("ingress")),
    Stream(5, "agw-app3-prod", "rg-app3-prod-web", "Microsoft.Network/applicationGateways", "agw", "Networking", 80, tags=_t3p("ingress")),
    Stream(5, "pip-app3-prod-ingress", "rg-app3-prod-web", "Microsoft.Network/publicIPAddresses", "egress", "Networking", 40, "prod_business", tags=_t3p("ingress")),
    Stream(6, "vpngw-app3-np", "rg-app3-np-network", "Microsoft.Network/virtualNetworkGateways", "vpn", "Networking", 10, "nonprod_247", tags=_t3n("connectivity")),
    # ---------------- Virtual Machines ----------------
    *[
        Stream(1, f"vm-app1-prod-batch0{i}", "rg-app1-prod-batch", VM, "e8s", "Virtual Machines", 12.1, tags=_t1p("batch"),
               reserved_from=date(2026, 2, 1), reserved_daily_amortized=9.0)
        for i in range(1, 5)
    ],
    Stream(1, "vm-app1-prod-jump", "rg-app1-prod-mgmt", VM, "b2ms", "Virtual Machines", 2.0, tags=_t1p("jumpbox")),
    Stream(2, "vm-app1-dev-build01", "rg-app1-np-build", VM, "d4s", "Virtual Machines", 80, "nonprod_office", tags=_t1n("build-agents")),
    Stream(2, "vm-app1-dev-tools", "rg-app1-np-build", VM, "d4s", "Virtual Machines", 46, "nonprod_247", tags=_t1n("tooling")),
    Stream(3, "vmss-app2-prod-workers", "rg-app2-prod-compute", VMSS, "d16s", "Virtual Machines", 650, tags=_t2p("workers")),
    Stream(4, "vm-app2-test-01", "rg-app2-np-compute", VM, "d8s", "Virtual Machines", 60, "nonprod_247", tags=_t2n("integration-test")),
    Stream(4, "vm-app2-test-02", "rg-app2-np-compute", VM, "d8s", "Virtual Machines", 60, "nonprod_247", tags=_t2n("integration-test")),
    Stream(4, "vm-app2-test-03", "rg-app2-np-compute", VM, "d8s", "Virtual Machines", 60, "nonprod_247", tags=_t2n("integration-test")),
    # New expensive GPU VM in Non-Production (created day 4 of the current week)
    Stream(4, "vm-app2-np-gpu01", "rg-app2-np-ml", VM, "nc6s", "Virtual Machines", 73.4, "nonprod_247",
           tags={"application": "app2", "environment": "test", "workload": "ml-experiment", "demo": "true"}, active_from="cur+3", growth=0.0),
    Stream(5, "vm-app3-prod-app01", "rg-app3-prod-compute", VM, "d8s", "Virtual Machines", 185, tags=_t3p("api")),
    Stream(5, "vm-app3-prod-app02", "rg-app3-prod-compute", VM, "d8s", "Virtual Machines", 185, tags=_t3p("api")),
    Stream(5, "vm-app3-prod-batch01", "rg-app3-prod-compute", VM, "d16s", "Virtual Machines", 140, tags=_t3p("batch")),
    Stream(6, "vm-sandbox-01", "rg-sandbox-experiments", VM, "d4s", "Virtual Machines", 45, "nonprod_247", tags={"demo": "true"}),
    Stream(6, "vm-app3-dev", "rg-app3-np-compute", VM, "d4s", "Virtual Machines", 60, "nonprod_office", tags=_t3n("api")),
    # ---------------- App Service ----------------
    Stream(1, "asp-app1-prod", "rg-app1-prod-web", "Microsoft.Web/serverfarms", "asp", "App Service", 260, tags=_t1p("web")),
    Stream(2, "asp-app1-np", "rg-app1-np-web", "Microsoft.Web/serverfarms", "asp", "App Service", 60, "nonprod_247", tags=_t1n("web")),
    Stream(3, "asp-app2-prod", "rg-app2-prod-web", "Microsoft.Web/serverfarms", "asp", "App Service", 340, tags=_t2p("web")),
    Stream(4, "asp-app2-np", "rg-app2-np-web", "Microsoft.Web/serverfarms", "asp", "App Service", 40, "nonprod_247", tags=_t2n("web")),
    Stream(5, "asp-app3-prod", "rg-app3-prod-web", "Microsoft.Web/serverfarms", "asp", "App Service", 380, tags=_t3p("web")),
    Stream(6, "asp-app3-np", "rg-app3-np-web", "Microsoft.Web/serverfarms", "asp", "App Service", 50, "nonprod_247", tags=_t3n("web")),
    # ---------------- Azure Monitor ----------------
    Stream(1, "log-app1-prod", "rg-app1-prod-mgmt", "Microsoft.OperationalInsights/workspaces", "la_ingest", "Azure Monitor", 380, "prod_business", tags=_t1p("observability"),
           events=[Event("scale", "cur+0", None, 1.10)]),
    Stream(1, "appi-app1-prod", "rg-app1-prod-mgmt", "Microsoft.Insights/components", "appi", "Azure Monitor", 60, "prod_business", tags=_t1p("observability")),
    Stream(2, "log-app1-np", "rg-app1-np-mgmt", "Microsoft.OperationalInsights/workspaces", "la_ingest", "Azure Monitor", 70, "nonprod_247", tags=_t1n("observability")),
    Stream(3, "log-app2-prod", "rg-app2-prod-mgmt", "Microsoft.OperationalInsights/workspaces", "la_ingest", "Azure Monitor", 220, "prod_business", tags=_t2p("observability")),
    Stream(4, "log-app2-np", "rg-app2-np-mgmt", "Microsoft.OperationalInsights/workspaces", "la_ingest", "Azure Monitor", 30, "nonprod_247", tags=_t2n("observability")),
    Stream(5, "log-app3-prod", "rg-app3-prod-mgmt", "Microsoft.OperationalInsights/workspaces", "la_ingest", "Azure Monitor", 200, "prod_business", tags=_t3p("observability"),
           events=[Event("spike", "prev-13", "prev-10", 2.2)]),
    Stream(6, "log-app3-np", "rg-app3-np-mgmt", "Microsoft.OperationalInsights/workspaces", "la_ingest", "Azure Monitor", 30, "nonprod_247", tags=_t3n("observability")),
    # ---------------- Key Vault ----------------
    Stream(1, "kv-app1-prod", "rg-app1-prod-mgmt", "Microsoft.KeyVault/vaults", "kv", "Key Vault", 55, tags=_t1p("secrets")),
    Stream(2, "kv-app1-np", "rg-app1-np-mgmt", "Microsoft.KeyVault/vaults", "kv", "Key Vault", 25, "nonprod_247", tags=_t1n("secrets")),
    Stream(3, "kv-app2-prod", "rg-app2-prod-mgmt", "Microsoft.KeyVault/vaults", "kv", "Key Vault", 45, tags=_t2p("secrets")),
    Stream(4, "kv-app2-np", "rg-app2-np-mgmt", "Microsoft.KeyVault/vaults", "kv", "Key Vault", 20, "nonprod_247", tags=_t2n("secrets")),
    Stream(5, "kv-app3-prod", "rg-app3-prod-mgmt", "Microsoft.KeyVault/vaults", "kv", "Key Vault", 40, tags=_t3p("secrets")),
    Stream(6, "kv-app3-np", "rg-app3-np-mgmt", "Microsoft.KeyVault/vaults", "kv", "Key Vault", 25, "nonprod_247", tags=_t3n("secrets")),
    # ---------------- Container Registry ----------------
    Stream(1, "acrapp1prod", "rg-app1-prod-aks", "Microsoft.ContainerRegistry/registries", "acr_storage", "Container Registry", 100, "storage", tags=_t1p("images")),
    Stream(2, "acrapp1np", "rg-app1-np-aks", "Microsoft.ContainerRegistry/registries", "acr", "Container Registry", 15, "nonprod_247", tags=_t1n("images")),
    Stream(3, "acrapp2prod", "rg-app2-prod-aks", "Microsoft.ContainerRegistry/registries", "acr_storage", "Container Registry", 80, "storage", tags=_t2p("images")),
    Stream(4, "acrapp2np", "rg-app2-np-aks", "Microsoft.ContainerRegistry/registries", "acr", "Container Registry", 15, "nonprod_247", tags=_t2n("images")),
    Stream(5, "acrapp3prod", "rg-app3-prod-aks", "Microsoft.ContainerRegistry/registries", "acr_storage", "Container Registry", 60, "storage", tags=_t3p("images")),
    Stream(6, "acrapp3np", "rg-app3-np-aks", "Microsoft.ContainerRegistry/registries", "acr", "Container Registry", 15, "nonprod_247", tags=_t3n("images")),
    # ---------------- Other services ----------------
    Stream(1, "rsv-app1-prod", "rg-app1-prod-mgmt", "Microsoft.RecoveryServices/vaults", "backup", "Other Services", 70, tags=_t1p("backup")),
    Stream(3, "rsv-app2-prod", "rg-app2-prod-mgmt", "Microsoft.RecoveryServices/vaults", "backup", "Other Services", 50, tags=_t2p("backup")),
    Stream(5, "rsv-app3-prod", "rg-app3-prod-mgmt", "Microsoft.RecoveryServices/vaults", "backup", "Other Services", 40, tags=_t3p("backup")),
    Stream(1, "defender-app1-prod", "rg-app1-prod-mgmt", "Microsoft.Security/pricings", "defender", "Other Services", 30, tags=_t1p("security")),
    Stream(3, "defender-app2-prod", "rg-app2-prod-mgmt", "Microsoft.Security/pricings", "defender", "Other Services", 30, tags=_t2p("security")),
    Stream(5, "defender-app3-prod", "rg-app3-prod-mgmt", "Microsoft.Security/pricings", "defender", "Other Services", 30, tags=_t3p("security")),
]

RESERVATION = {
    "subscription": 1,
    "purchase_date": date(2026, 2, 1),
    "amount": Decimal("13140.00"),
    "name": "RI-E8s_v5-eastus-1yr-x4 (DEMO)",
    "id": "/providers/Microsoft.Capacity/reservationOrders/de000000-0000-4000-8000-0000000000f1/reservations/de000000-0000-4000-8000-0000000000f2",
}
REFUND = {"subscription": 5, "date": date(2026, 9, 14), "resource": "asp-app3-prod", "amount": Decimal("-150.00")}
