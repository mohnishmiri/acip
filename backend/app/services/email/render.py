"""Render notification emails (HTML + plain text) from database records.

Every figure comes from the underlying record (anomaly, budget, savings opportunity,
ingestion job, subscription) -- nothing is invented for the message. Measured facts and
suggested next steps are kept visibly separate, as in the application.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AlertRule, AzureSubscription, Budget, CostAnomaly, IngestionJob, NotificationHistory, SavingsOpportunity

_TEMPLATES = Path(__file__).resolve().parents[2] / "templates" / "email"
_html_env = Environment(loader=FileSystemLoader(_TEMPLATES), autoescape=select_autoescape(["html"]), undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
_text_env = Environment(loader=FileSystemLoader(_TEMPLATES), autoescape=False, undefined=StrictUndefined, keep_trailing_newline=True)

SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥", "AUD": "A$", "CAD": "C$"}
SEVERITY = {
    "critical": {"label": "CRITICAL", "fg": "#9b1c1c", "bg": "#fdeeee", "border": "#f1b8b8", "dot": "#d03b3b", "accent": "#d03b3b"},
    "high": {"label": "HIGH", "fg": "#8f3a14", "bg": "#fdf0ea", "border": "#f2c2ad", "dot": "#ec835a", "accent": "#ec835a"},
    "medium": {"label": "MEDIUM", "fg": "#7a5200", "bg": "#fff7e3", "border": "#f6d98d", "dot": "#e0a000", "accent": "#fab219"},
    "low": {"label": "LOW", "fg": "#0c4f8c", "bg": "#ebf3fc", "border": "#b9d5f2", "dot": "#2a78d6", "accent": "#7aa7d9"},
    "informational": {"label": "INFO", "fg": "#4a4d52", "bg": "#f2f3f5", "border": "#dde0e4", "dot": "#9aa0a6", "accent": "#a3a7ad"},
}
KIND = {
    "anomaly": "Cost anomaly",
    "budget_threshold": "Budget alert",
    "budget_forecast": "Forecast alert",
    "ingestion_failure": "Data ingestion",
    "data_delay": "Data freshness",
    "savings_opportunity": "Potential savings",
    "test": "Email delivery test",
}
SUBJECT_TAG = {
    "anomaly": None,  # severity is used instead
    "budget_threshold": "Budget",
    "budget_forecast": "Forecast",
    "ingestion_failure": "Action required",
    "data_delay": "Data delay",
    "savings_opportunity": "Savings",
    "test": "Test",
}


@dataclass
class RenderedEmail:
    subject: str
    html: str
    text: str


def money(v: Any, currency: str = "USD", sign: bool = False) -> str:
    if v is None:
        return "—"
    d = Decimal(str(v))
    sym = SYMBOL.get(currency, "")
    s = f"{sym}{abs(d):,.2f}" if sym else f"{abs(d):,.2f} {currency}"
    if d < 0:
        return f"-{s}"
    return f"+{s}" if sign and d > 0 else s


def pct(v: Any, sign: bool = True) -> str:
    if v is None:
        return "n/a"
    d = Decimal(str(v))
    return f"{'+' if sign and d > 0 else ''}{d:,.1f}%"


def long_date(d: date | datetime | str | None) -> str:
    if d is None:
        return "—"
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return d.strftime("%d %b %Y")


def _url(path: str | None) -> str:
    base = get_settings().app_public_url.rstrip("/")
    return f"{base}{path or '/'}"


def _base(n: NotificationHistory | None, rule: AlertRule | None, *, kind: str, is_demo: bool) -> dict[str, Any]:
    s = get_settings()
    reason = (
        f"You are receiving this because you are a recipient of the alert rule “{rule.name}”."
        if rule is not None
        else "You are receiving this message because an administrator sent it from Alerts & Notifications."
    )
    return {
        "brand": {"name": s.email_from_name, "product": "Azure Cost Intelligence", "public_url": _url("/"),
                  "tagline": s.email_from_name if s.email_from_name.strip().lower() != "azure cost intelligence" else "Cost monitoring for Azure"},
        "kind_label": KIND.get(kind, "Notification"),
        "is_demo": is_demo,
        "severity": None,
        "accent": "#0f6cbd",
        "eyebrow": "",
        "metrics": [],
        "progress": None,
        "details": [],
        "sections": [],
        "cta": None,
        "secondary": {"label": "View all alerts", "url": _url("/alerts")},
        "footer_lines": [reason, "ACIP is read-only: it reports on Azure billing data and never changes Azure resources."],
        "manage_url": _url("/alerts?tab=rules"),
        "reference": f"ACIP-N{n.id:07d}" if n is not None and n.id else "ACIP-TEST",
    }


def _with_severity(ctx: dict[str, Any], severity: str | None) -> None:
    sev = SEVERITY.get(severity or "")
    if sev:
        ctx["severity"] = sev
        ctx["accent"] = sev["accent"]


def _subject(kind: str, title: str, *, severity: str | None, suffix: str = "", is_demo: bool = False) -> str:
    tag = SUBJECT_TAG.get(kind)
    if kind == "anomaly" and severity:
        tag = f"{severity.capitalize()} severity"
    prefix = "[DEMO] " if is_demo else ""
    subject = f"{prefix}[ACIP{' · ' + tag if tag else ''}] {title}{suffix}"
    return subject[:240]


# -------------------------------------------------------------------- per type context --

def _anomaly(db: Session, n: NotificationHistory, ctx: dict[str, Any]) -> str:
    from app.services.labels import LabelResolver

    a = db.get(CostAnomaly, int(n.entity_id)) if n.entity_id and n.entity_id.isdigit() else None
    if a is None:
        return _generic(n, ctx)
    labels = LabelResolver(db)
    cur = a.billing_currency
    _with_severity(ctx, a.severity)
    ref = f"ANM-{a.id:06d}"
    ctx["eyebrow"] = f"{ref} · detected {long_date(a.detection_date)}"
    ctx["title"] = a.title
    obs = (a.evidence or {}).get("observed_period") or {}
    p_start = date.fromisoformat(obs["start"]) if obs.get("start") else a.period_start
    p_end = date.fromisoformat(obs["end"]) if obs.get("end") else a.period_end
    period = long_date(p_start) if p_start == p_end else f"{long_date(p_start)} – {long_date(p_end)}"
    pct_txt = f" ({pct(a.percentage_increase)})" if a.percentage_increase is not None else ""
    ctx["lead"] = (
        f"Spend for {period} was {money(a.current_cost, cur)}, {money(a.absolute_increase, cur)}{pct_txt} above the expected "
        f"baseline of {money(a.expected_baseline, cur)}. This exceeded the configured threshold for the rule “{a.evidence.get('rule', {}).get('name', a.rule_code)}”."
    )
    ctx["metrics"] = [
        {"label": "Observed cost", "value": money(a.current_cost, cur), "sub": period},
        {"label": "Expected baseline", "value": money(a.expected_baseline, cur), "sub": (a.evidence or {}).get("baseline_description", "")[:60]},
        {"label": "Increase", "value": money(a.absolute_increase, cur, sign=True), "sub": pct(a.percentage_increase) if a.percentage_increase is not None else "new spend", "color": "#b42318"},
    ]
    _, app_name = labels.application(a.application_id, None) if a.application_id is not None else ("", "—")
    _, env_name = labels.environment(a.environment_id) if a.environment_id is not None else ("", "—")
    _, sub_name = labels.subscription(a.subscription_fk) if a.subscription_fk is not None else ("", "—")
    details = [("Anomaly ID", ref), ("Application", app_name), ("Environment", env_name), ("Subscription", sub_name)]
    if a.service_category:
        details.append(("Azure service", a.service_category))
    if a.resource_name:
        details.append(("Resource", a.resource_name))
    if a.resource_group:
        details.append(("Resource group", a.resource_group))
    details += [("Detection rule", (a.evidence or {}).get("rule", {}).get("name", a.rule_code)), ("Cost basis", f"{a.dataset_type.capitalize()} cost · {cur}")]
    if a.occurrence_count > 1:
        details.append(("Ongoing", f"Detected on {a.occurrence_count} days, last on {long_date(a.last_detected_date)}"))
    ctx["details"] = details
    sections = [{"heading": "What we measured", "paragraphs": [a.explanation]}]
    meters = [m for m in (a.evidence or {}).get("top_meters", []) if m.get("diff")][:4]
    if meters:
        sections.append({
            "heading": "Largest contributing meters",
            "table": {
                "headers": ["Meter", "Baseline", "Observed", "Change"],
                "rows": [[m.get("meter_name") or "—", money(m.get("baseline_cost"), cur), money(m.get("observed_cost"), cur), money(m.get("diff"), cur, sign=True)] for m in meters],
            },
        })
    steps = list(a.recommended_steps or [])[:4]
    if steps:
        sections.append({"heading": "Suggested next steps", "bullets": steps, "ordered": True,
                         "note": "Suggested investigation steps, not confirmed causes. Billing data shows what changed, not why."})
    ctx["sections"] = sections
    ctx["cta"] = {"label": "Investigate anomaly", "url": _url(f"/anomalies/{a.id}")}
    ctx["preheader"] = f"{money(a.absolute_increase, cur, sign=True)}{pct_txt} vs baseline · {sub_name}"
    suffix = f" ({money(a.absolute_increase, cur, sign=True)}{', ' + pct(a.percentage_increase) if a.percentage_increase is not None else ''})"
    return _subject("anomaly", a.title, severity=a.severity, suffix=suffix, is_demo=n.is_demo)


def _budget(db: Session, n: NotificationHistory, ctx: dict[str, Any], forecast: bool) -> str:
    from app.services import budget_service
    from app.services.labels import LabelResolver

    b = db.get(Budget, int(n.entity_id)) if n.entity_id and n.entity_id.isdigit() else None
    if b is None:
        return _generic(n, ctx)
    st = budget_service.evaluate_budget(db, b, LabelResolver(db))
    cur = st["currency"]
    util = st["utilization_pct"] or 0
    fu = st["forecast_utilization_pct"] or 0
    _with_severity(ctx, n.severity)
    ctx["eyebrow"] = f"{st['scope_label']} · {st['period_type'].capitalize()} budget · {long_date(st['period_start'])} – {long_date(st['period_end'])}"
    ctx["title"] = n.title
    if forecast:
        ctx["lead"] = (
            f"At the current pace, spend for “{b.name}” is projected to reach {money(st['forecast'], cur)} by {long_date(st['period_end'])}, "
            f"{money(st['forecast_variance'], cur)} above the budget of {money(st['amount'], cur)}. The projection uses the {st['forecast_method_label'].lower()} method."
        )
        ctx["metrics"] = [
            {"label": "Budget", "value": money(st["amount"], cur), "sub": f"{st['period_type']} amount"},
            {"label": "Forecast", "value": money(st["forecast"], cur), "sub": f"{pct(fu, sign=False)} of budget"},
            {"label": "Projected overspend", "value": money(st["forecast_variance"], cur, sign=True), "sub": "projection, not an actual charge", "color": "#b42318"},
        ]
    else:
        ctx["lead"] = (
            f"Spend for “{b.name}” has reached {money(st['actual'], cur)}, {pct(util, sign=False)} of the {money(st['amount'], cur)} budget, "
            f"with {st['remaining_days']} day(s) remaining in the period."
        )
        ctx["metrics"] = [
            {"label": "Spent to date", "value": money(st["actual"], cur), "sub": f"through {long_date(st['as_of'])}"},
            {"label": "Budget", "value": money(st["amount"], cur), "sub": f"remaining {money(st['remaining'], cur)}"},
            {"label": "Utilisation", "value": pct(util, sign=False), "sub": f"forecast {pct(fu, sign=False)}", "color": "#b42318" if util >= 100 else None},
        ]
    bar_color = "#d03b3b" if util >= 100 else "#ec835a" if util >= 90 else "#0f6cbd"
    ctx["progress"] = {"pct": int(max(0, min(util, 100))), "color": bar_color,
                       "label": f"{pct(util, sign=False)} of budget used",
                       "note": f"Forecast at period end: {money(st['forecast'], cur)} ({pct(fu, sign=False)}) — {st['forecast_method_label']}."}
    ctx["details"] = [
        ("Budget", b.name), ("Scope", st["scope_label"]), ("Period", f"{long_date(st['period_start'])} – {long_date(st['period_end'])}"),
        ("Daily run rate", money(st["daily_run_rate"], cur)), ("Alert thresholds", ", ".join(f"{float(t):g}%" for t in (st["thresholds"] or []))),
        ("Cost basis", f"{st['cost_type'].capitalize()} cost · {cur}"),
    ]
    ctx["sections"] = [{
        "heading": "Suggested next steps",
        "ordered": True,
        "bullets": [
            "Review the largest cost increases for this scope in Cost Comparison.",
            "Check open cost anomalies for the same application or subscription.",
            "Confirm with the budget owner whether the spend is planned; adjust the budget if the plan has changed.",
        ],
    }]
    ctx["cta"] = {"label": "Review budget", "url": _url("/budgets")}
    ctx["preheader"] = f"{pct(util, sign=False)} used · forecast {money(st['forecast'], cur)} of {money(st['amount'], cur)}"
    return _subject("budget_forecast" if forecast else "budget_threshold", n.title, severity=n.severity, is_demo=n.is_demo)


def _savings(db: Session, n: NotificationHistory, ctx: dict[str, Any]) -> str:
    o = db.get(SavingsOpportunity, int(n.entity_id)) if n.entity_id and n.entity_id.isdigit() else None
    if o is None:
        return _generic(n, ctx)
    cur = o.billing_currency
    ctx["eyebrow"] = f"Source: {'Azure Advisor' if o.evidence_source == 'azure_advisor' else 'billing analysis'}"
    ctx["title"] = o.title
    ctx["lead"] = o.issue
    ctx["metrics"] = [
        {"label": "Estimated savings", "value": f"{money(o.estimated_monthly_savings, cur)}/mo" if o.estimated_monthly_savings is not None else "Not estimated", "sub": "estimate, not realised", "color": "#006300"},
        {"label": "Current monthly cost", "value": money(o.current_monthly_cost, cur), "sub": o.service_category or ""},
    ]
    ctx["details"] = [("Resource", o.resource_name or "—"), ("Basis of estimate", o.savings_basis or "—"), ("Status", o.status.capitalize())]
    ctx["sections"] = [{"heading": "Recommendation", "paragraphs": [o.recommendation],
                        "note": "ACIP never changes Azure resources. Any change must be reviewed and made by the resource owner."}]
    ctx["cta"] = {"label": "Review opportunity", "url": _url("/savings")}
    ctx["preheader"] = n.message[:120]
    return _subject("savings_opportunity", n.title.replace("Potential savings: ", ""), severity=None, is_demo=n.is_demo)


def _ingestion(db: Session, n: NotificationHistory, ctx: dict[str, Any]) -> str:
    job = db.get(IngestionJob, int(n.entity_id)) if n.entity_id and n.entity_id.isdigit() else None
    _with_severity(ctx, n.severity)
    ctx["title"] = n.title
    ctx["eyebrow"] = f"Job {job.id} · {job.job_type.replace('_', ' ')}" if job else "Ingestion job"
    ctx["lead"] = "A data ingestion job failed after all automatic retries. Reports for the affected subscription may be incomplete until it succeeds."
    if job:
        ctx["details"] = [("Job", f"#{job.id} ({job.job_type})"), ("Attempts", f"{job.attempts} of {job.max_attempts}"),
                          ("Started", job.started_at.strftime("%d %b %Y %H:%M UTC") if job.started_at else "—"), ("Triggered by", job.triggered_by)]
    ctx["sections"] = [
        {"heading": "Error", "code": n.message[:1500]},
        {"heading": "Suggested next steps", "ordered": True, "bullets": [
            "Run “Test” for the subscription in Administration → Azure Connections.",
            "Check the job's errors and logs in Data Management, then use Retry.",
            "If the error mentions permissions, confirm Cost Management Reader / Storage Blob Data Reader for the collection service principal.",
        ]},
    ]
    ctx["cta"] = {"label": "Open Data Management", "url": _url("/data-management")}
    ctx["preheader"] = n.message[:120]
    return _subject("ingestion_failure", n.title, severity=None, is_demo=n.is_demo)


def _data_delay(db: Session, n: NotificationHistory, ctx: dict[str, Any]) -> str:
    sub = db.execute(select(AzureSubscription).where(AzureSubscription.subscription_id == (n.entity_id or ""))).scalar_one_or_none()
    _with_severity(ctx, n.severity)
    ctx["title"] = n.title
    ctx["eyebrow"] = sub.subscription_id if sub else ""
    ctx["lead"] = "New billing data has not arrived for this subscription within the expected window. Dashboards continue to show the last data received."
    if sub:
        ctx["details"] = [("Subscription", sub.subscription_name),
                          ("Last successful ingestion", sub.last_successful_sync_at.strftime("%d %b %Y %H:%M UTC") if sub.last_successful_sync_at else "never"),
                          ("Last error", sub.last_sync_error or "—")]
    ctx["sections"] = [{"heading": "Status", "paragraphs": [n.message]}]
    ctx["cta"] = {"label": "Open Data Management", "url": _url("/data-management")}
    ctx["preheader"] = n.message[:120]
    return _subject("data_delay", n.title, severity=None, is_demo=n.is_demo)


def _generic(n: NotificationHistory, ctx: dict[str, Any]) -> str:
    _with_severity(ctx, n.severity)
    ctx["title"] = n.title
    ctx["lead"] = n.message
    ctx["cta"] = {"label": "Open in ACIP", "url": _url(n.link or "/alerts")}
    ctx["preheader"] = n.message[:120]
    return _subject(n.notification_type, n.title, severity=n.severity if n.notification_type == "anomaly" else None, is_demo=n.is_demo)


def render_notification(db: Session, n: NotificationHistory) -> RenderedEmail:
    rule = db.get(AlertRule, n.alert_rule_id) if n.alert_rule_id else None
    ctx = _base(n, rule, kind=n.notification_type, is_demo=n.is_demo)
    ctx.setdefault("lead", "")
    ctx.setdefault("title", n.title)
    ctx.setdefault("preheader", "")
    if n.notification_type == "anomaly":
        subject = _anomaly(db, n, ctx)
    elif n.notification_type in ("budget_threshold", "budget_forecast"):
        subject = _budget(db, n, ctx, forecast=n.notification_type == "budget_forecast")
    elif n.notification_type == "savings_opportunity":
        subject = _savings(db, n, ctx)
    elif n.notification_type == "ingestion_failure":
        subject = _ingestion(db, n, ctx)
    elif n.notification_type == "data_delay":
        subject = _data_delay(db, n, ctx)
    else:
        subject = _generic(n, ctx)
    ctx["footer_lines"].append(f"Notification created {n.created_at.strftime('%d %b %Y %H:%M UTC') if n.created_at else ''}. "
                               "Current-month charges are estimates until the invoice is finalised.")
    return _render(ctx, subject)


def render_test(recipients: list[str]) -> RenderedEmail:
    s = get_settings()
    ctx = _base(None, None, kind="test", is_demo=False)
    ctx.update(
        title="Email delivery is working",
        eyebrow=datetime.now(UTC).strftime("Sent %d %b %Y %H:%M UTC"),
        lead="This test message confirms that Azure Cost Intelligence can deliver alert emails to this address. "
             "Alert rules with the Email channel will send cost anomaly, budget, forecast, data-ingestion and savings alerts in this format.",
        metrics=[
            {"label": "Delivery", "value": "Successful", "sub": f"via {s.email_provider.upper()}", "color": "#006300"},
            {"label": "Sender", "value": s.email_from_name, "sub": s.email_from_address},
        ],
        details=[("Recipients", ", ".join(recipients)), ("Links point to", s.app_public_url)],
        sections=[{"heading": "What happens next", "ordered": True, "bullets": [
            "Open Alerts & Notifications → Alert rules and edit a rule.",
            "Select the Email channel and add the recipients who should receive it.",
            "Each new alert is emailed once; ongoing issues are not re-sent.",
        ]}],
        cta={"label": "Manage alert rules", "url": _url("/alerts?tab=rules")},
        preheader="Test message: alert email delivery from Azure Cost Intelligence is configured correctly.",
    )
    return _render(ctx, _subject("test", "Email delivery test", severity=None))


def _normalise(ctx: dict[str, Any]) -> None:
    """Give optional template fields explicit defaults (templates use StrictUndefined to catch typos)."""
    ctx["metrics"] = [{"sub": "", "color": None, **m} for m in ctx.get("metrics") or []]
    ctx["sections"] = [{"paragraphs": [], "table": None, "bullets": [], "ordered": False, "code": None, "note": None, **s} for s in ctx.get("sections") or []]
    if ctx.get("progress"):
        ctx["progress"] = {"note": None, **ctx["progress"]}


def _render(ctx: dict[str, Any], subject: str) -> RenderedEmail:
    _normalise(ctx)
    ctx["subject"] = subject
    html = _html_env.get_template("notification.html").render(**ctx)
    text = _text_env.get_template("notification.txt").render(**ctx)
    return RenderedEmail(subject=subject, html=html, text=text)
