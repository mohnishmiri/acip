"""CSV / Excel exports that respect the applied filters and state the reporting context."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.services import resource_service
from app.services.params import ReportParams
from app.services.reporting_service import ReportingService

MAX_EXPORT_ROWS = 100_000

COLUMNS: dict[str, list[tuple[str, str]]] = {
    "groups": [
        ("label", "Group"), ("key", "Key"), ("previous", "Previous cost"), ("current", "Current cost"), ("diff", "Difference"),
        ("pct", "Change %"), ("status", "Status"), ("share_of_total", "Share of total %"), ("contribution_pct", "Contribution to change %"),
        ("previous_daily_avg", "Previous daily avg"), ("current_daily_avg", "Current daily avg"), ("current_records", "Records (current)"),
    ],
    "resources": [
        ("resource_name", "Resource name"), ("resource_id", "Resource ID"), ("application", "Application"), ("environment", "Environment"),
        ("subscription_name", "Subscription"), ("resource_group", "Resource group"), ("service_category", "Service"),
        ("resource_type", "Resource type"), ("region", "Region"), ("owner", "Owner"), ("cost_center", "Cost center"),
        ("previous", "Previous cost"), ("current", "Current cost"), ("diff", "Difference"), ("pct", "Change %"), ("status", "Status"),
        ("primary_meter_name", "Primary meter"), ("primary_meter_category", "Meter category"), ("primary_meter_quantity", "Usage quantity"),
        ("primary_meter_unit", "Unit"), ("billing_currency", "Currency"), ("tags_text", "Tags"),
    ],
    "records": [
        ("usage_date", "Date"), ("subscription_name", "Subscription"), ("resource_name", "Resource"), ("resource_group", "Resource group"),
        ("service_category", "Service"), ("meter_category", "Meter category"), ("meter_subcategory", "Meter subcategory"),
        ("meter_name", "Meter"), ("sku", "SKU"), ("quantity", "Quantity"), ("unit_of_measure", "Unit"), ("effective_price", "Effective price"),
        ("cost", "Cost"), ("billing_currency", "Currency"), ("charge_type", "Charge type"), ("pricing_model", "Pricing model"),
        ("benefit_name", "Benefit"), ("region", "Region"), ("export_run_id", "Export run"), ("ingestion_file_id", "Source file"),
        ("source_row_number", "Source row"),
    ],
}


def _rows_for(db: Session, params: ReportParams, view: str, allowed: set[int] | None) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    if view in ("explorer", "compare", "contributors"):
        p = params.copy(page=1, page_size=MAX_EXPORT_ROWS)
        out = ReportingService(db, p, allowed).contributors()
        return "groups", out["data"], out["meta"]
    if view == "resources":
        out = resource_service.list_resources(db, params.copy(page=1, page_size=MAX_EXPORT_ROWS), allowed)
        for r in out["data"]:
            pm = r.get("primary_meter") or {}
            r["primary_meter_name"] = pm.get("meter_name")
            r["primary_meter_category"] = pm.get("meter_category")
            r["primary_meter_quantity"] = pm.get("quantity")
            r["primary_meter_unit"] = pm.get("unit")
            r["tags_text"] = "; ".join(f"{k}={v}" for k, v in (r.get("tags") or {}).items())
        return "resources", out["data"], out["meta"]
    if view == "records":
        out = resource_service.billing_records(db, params.copy(page=1, page_size=MAX_EXPORT_ROWS), allowed)
        for r in out["data"]:
            r.pop("tags", None)
        return "records", out["data"], out["meta"]
    raise ValidationFailed("view must be explorer, compare, contributors, resources or records")


def _context_rows(meta: dict[str, Any], params: ReportParams, view: str) -> list[list[Any]]:
    period = meta.get("period") or {}
    cmp_ = meta.get("comparison_period")
    filters = []
    for name in ("application", "environment", "subscription", "service_category", "resource_group", "resource", "region", "owner",
                 "cost_center", "meter_category", "meter_name", "sku", "tag", "charge_type", "pricing_model"):
        vals = getattr(params, name)
        if vals:
            filters.append(f"{name}={'|'.join(vals)}")
    if params.search:
        filters.append(f"search={params.search}")
    rows = [
        ["Azure Cost Intelligence Platform — export"],
        ["View", view],
        ["Reporting period", f"{period.get('start')} to {period.get('end')} ({period.get('label')})"],
        ["Comparison period", f"{cmp_['start']} to {cmp_['end']} ({cmp_['label']})" if cmp_ else "None"],
        ["Currency", meta.get("currency")],
        ["Cost type", meta.get("cost_type")],
        ["Group by", params.group_by],
        ["Filters", "; ".join(filters) or "None"],
        ["Data as of (latest usage date)", meta.get("as_of")],
        ["Generated (UTC)", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")],
    ]
    if meta.get("is_demo"):
        rows.append(["DATA", "DEMO DATA — synthetic values, not actual Azure billing"])
    for w in meta.get("warnings") or []:
        rows.append(["Note", w])
    rows.append([])
    return rows


def build_export(db: Session, params: ReportParams, view: str, fmt: str, allowed: set[int] | None) -> tuple[str, bytes, str]:
    kind, data, meta = _rows_for(db, params, view, allowed)
    cols = COLUMNS[kind]
    ctx = _context_rows(meta, params, view)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    period = meta.get("period") or {}
    base = f"acip-{view}-{period.get('start', '')}_{period.get('end', '')}-{meta.get('currency', '')}-{stamp}"
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        for r in ctx:
            w.writerow(r)
        w.writerow([h for _, h in cols])
        for row in data:
            w.writerow([row.get(k) for k, _ in cols])
        return f"{base}.csv", buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = "Data"
        for r in ctx:
            ws.append(r)
        for cell in ws["A"][: len(ctx)]:
            cell.font = Font(bold=True)
        header_row = len(ctx) + 1
        ws.append([h for _, h in cols])
        for c in ws[header_row]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="0F6CBD")
        money_cols = {i + 1 for i, (k, _) in enumerate(cols) if k in ("previous", "current", "diff", "cost", "previous_daily_avg", "current_daily_avg")}
        for row in data:
            ws.append([row.get(k) for k, _ in cols])
        for col_idx in money_cols:
            for cell in ws.iter_rows(min_row=header_row + 1, min_col=col_idx, max_col=col_idx):
                cell[0].number_format = "#,##0.00;[Red]-#,##0.00"
        for i, (_, h) in enumerate(cols, start=1):
            ws.column_dimensions[get_column_letter(i)].width = max(12, min(48, len(h) + 4))
        ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
        out = io.BytesIO()
        wb.save(out)
        return f"{base}.xlsx", out.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    raise ValidationFailed("format must be csv or xlsx")
