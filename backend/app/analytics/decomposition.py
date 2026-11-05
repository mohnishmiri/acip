"""Meter-level root-cause decomposition ("what exactly changed?").

The change between two periods is decomposed at the finest grain available --
(resource, meter, charge type, pricing model) -- into mutually exclusive effects that sum
exactly to the total difference:

    volume            (q1 - q0) * p0              same meter, quantity moved
    price             (p1 - p0) * q1              same meter, effective unit price moved
    new_meter         c1                          meter billed now but not before (resource existed)
    removed_meter     -c0                         meter billed before but not now
    new_resource      c1                          resource had no records in comparison period
    removed_resource  -c0                         resource has no records in current period
    commitment        change where usage moved between on-demand and reservation/savings plan
    credits_refunds   refunds / negative adjustments
    other_charges     purchases, taxes, rounding and other non-usage charge types
    unpriced          usage rows without quantity (cannot be split into price/volume)

Effective price is derived from billed cost / billed quantity; it reflects discounts and
commitments, not list price. Billing data alone cannot prove *why* quantity or price
moved -- statements produced here are split into confirmed billing facts and explicitly
labelled hypotheses.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.analytics.comparison import ZERO, money, pct_change, price, qty, to_decimal

EFFECT_LABELS = {
    "volume": "Usage quantity change",
    "price": "Effective price change",
    "new_meter": "New meters (SKU/meter change)",
    "removed_meter": "Removed meters",
    "new_resource": "New resources",
    "removed_resource": "Removed resources",
    "commitment": "Reservation / Savings Plan changes",
    "credits_refunds": "Credits, refunds & negative adjustments",
    "other_charges": "Purchases, taxes & other charges",
    "unpriced": "Charges without quantity",
}


@dataclass
class MeterRow:
    resource_key: str
    resource_name: str | None
    meter_key: str
    meter_category: str | None
    meter_subcategory: str | None
    meter_name: str | None
    unit: str | None
    charge_type: str | None
    pricing_model: str | None
    sku: str | None = None
    prev_cost: Decimal = ZERO
    cur_cost: Decimal = ZERO
    prev_qty: Decimal = ZERO
    cur_qty: Decimal = ZERO
    prev_records: int = 0
    cur_records: int = 0
    effects: dict[str, Decimal] = field(default_factory=dict)
    classification: str = ""

    @property
    def diff(self) -> Decimal:
        return self.cur_cost - self.prev_cost


def _is_usage(charge_type: str | None) -> bool:
    return (charge_type or "usage").strip().lower() in ("usage", "")


def _is_commitment(pricing_model: str | None) -> bool:
    return (pricing_model or "").strip().lower() in ("reservation", "savingsplan", "savings plan", "spot")


def decompose(rows: list[MeterRow]) -> dict[str, Any]:
    resource_prev: dict[str, int] = defaultdict(int)
    resource_cur: dict[str, int] = defaultdict(int)
    for r in rows:
        resource_prev[r.resource_key] += r.prev_records
        resource_cur[r.resource_key] += r.cur_records

    # (resource, meter) pairs present per pricing model in each period -- used to detect
    # usage moving between on-demand and commitment pricing.
    pm_prev: dict[tuple[str, str], set[str]] = defaultdict(set)
    pm_cur: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in rows:
        if r.prev_records:
            pm_prev[(r.resource_key, r.meter_key)].add((r.pricing_model or "").lower())
        if r.cur_records:
            pm_cur[(r.resource_key, r.meter_key)].add((r.pricing_model or "").lower())

    for r in rows:
        d = r.diff
        ct = (r.charge_type or "").strip().lower()
        if not _is_usage(r.charge_type):
            if ct in ("refund", "credit", "adjustment") or (r.cur_cost < ZERO or r.prev_cost < ZERO):
                r.classification = "credits_refunds"
            elif ct in ("unusedreservation", "unusedsavingsplan"):
                r.classification = "commitment"
            else:
                r.classification = "other_charges"
            r.effects = {r.classification: d}
            continue
        if resource_prev[r.resource_key] == 0 and resource_cur[r.resource_key] > 0:
            r.classification = "new_resource"
            r.effects = {"new_resource": d}
            continue
        if resource_cur[r.resource_key] == 0 and resource_prev[r.resource_key] > 0:
            r.classification = "removed_resource"
            r.effects = {"removed_resource": d}
            continue
        pair = (r.resource_key, r.meter_key)
        if r.prev_records == 0 or r.cur_records == 0:
            other_models_prev = pm_prev.get(pair, set()) - {(r.pricing_model or "").lower()}
            other_models_cur = pm_cur.get(pair, set()) - {(r.pricing_model or "").lower()}
            moved = (r.prev_records == 0 and other_models_prev) or (r.cur_records == 0 and other_models_cur)
            if moved and (_is_commitment(r.pricing_model) or any(_is_commitment(m) for m in other_models_prev | other_models_cur)):
                r.classification = "commitment"
                r.effects = {"commitment": d}
            elif r.prev_records == 0:
                r.classification = "new_meter"
                r.effects = {"new_meter": d}
            else:
                r.classification = "removed_meter"
                r.effects = {"removed_meter": d}
            continue
        if r.prev_qty > ZERO and r.cur_qty > ZERO:
            p0 = r.prev_cost / r.prev_qty
            volume = (r.cur_qty - r.prev_qty) * p0
            r.classification = "volume_price"
            r.effects = {"volume": volume, "price": d - volume}
        else:
            r.classification = "unpriced"
            r.effects = {"unpriced": d}

    totals: dict[str, Decimal] = {k: ZERO for k in EFFECT_LABELS}
    for r in rows:
        for k, v in r.effects.items():
            totals[k] += v
    total_prev = sum((r.prev_cost for r in rows), ZERO)
    total_cur = sum((r.cur_cost for r in rows), ZERO)
    total_diff = total_cur - total_prev
    effects_sum = sum(totals.values(), ZERO)

    meters = _rollup_meters(rows)
    resources = _rollup_resources(rows, resource_prev, resource_cur)
    facts, hypotheses = _statements(meters, resources, totals, rows)

    return {
        "previous_total": money(total_prev),
        "current_total": money(total_cur),
        "difference": money(total_diff),
        "pct_change": money(pct_change(total_prev, total_cur)),
        "reconciled": effects_sum == total_diff,
        "effects": [
            {"key": k, "label": EFFECT_LABELS[k], "value": money(v), "share_of_change": money(v / total_diff * 100) if total_diff != ZERO else None}
            for k, v in totals.items()
            if abs(v) >= Decimal("0.005")  # suppress sub-cent residue from quantity rounding
        ],
        "meters": meters,
        "resources": resources,
        "confirmed_facts": facts,
        "hypotheses": hypotheses,
    }


def _rollup_meters(rows: list[MeterRow]) -> list[dict[str, Any]]:
    agg: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        k = (r.meter_key, r.charge_type or "", r.pricing_model or "")
        a = agg.setdefault(
            k,
            {
                "meter_key": r.meter_key,
                "meter_category": r.meter_category,
                "meter_subcategory": r.meter_subcategory,
                "meter_name": r.meter_name,
                "unit": r.unit,
                "charge_type": r.charge_type,
                "pricing_model": r.pricing_model,
                "sku": r.sku,
                "prev_cost": ZERO,
                "cur_cost": ZERO,
                "prev_qty": ZERO,
                "cur_qty": ZERO,
                "prev_records": 0,
                "cur_records": 0,
                "effects": defaultdict(lambda: ZERO),
                "resources": set(),
            },
        )
        a["prev_cost"] += r.prev_cost
        a["cur_cost"] += r.cur_cost
        a["prev_qty"] += r.prev_qty
        a["cur_qty"] += r.cur_qty
        a["prev_records"] += r.prev_records
        a["cur_records"] += r.cur_records
        a["resources"].add(r.resource_key)
        for ek, ev in r.effects.items():
            a["effects"][ek] += ev

    out = []
    for a in agg.values():
        pc, cc, pq, cq = a["prev_cost"], a["cur_cost"], a["prev_qty"], a["cur_qty"]
        p0 = pc / pq if pq > ZERO else None
        p1 = cc / cq if cq > ZERO else None
        if a["prev_records"] == 0:
            status = "new"
        elif a["cur_records"] == 0:
            status = "removed"
        else:
            status = "changed" if cc != pc else "unchanged"
        out.append(
            {
                "meter_key": a["meter_key"],
                "meter_category": a["meter_category"],
                "meter_subcategory": a["meter_subcategory"],
                "meter_name": a["meter_name"],
                "unit": a["unit"],
                "charge_type": a["charge_type"],
                "pricing_model": a["pricing_model"],
                "sku": a["sku"],
                "status": status,
                "previous_quantity": qty(pq),
                "current_quantity": qty(cq),
                "quantity_diff": qty(cq - pq),
                "quantity_pct": money(pct_change(pq, cq)),
                "previous_cost": money(pc),
                "current_cost": money(cc),
                "difference": money(cc - pc),
                "pct_change": money(pct_change(pc, cc)),
                "previous_unit_price": price(p0),
                "current_unit_price": price(p1),
                "unit_price_pct": money(pct_change(p0, p1)) if p0 is not None and p1 is not None else None,
                "volume_effect": money(a["effects"].get("volume", ZERO)),
                "price_effect": money(a["effects"].get("price", ZERO)),
                "other_effect": money(sum((v for k, v in a["effects"].items() if k not in ("volume", "price")), ZERO)),
                "resource_count": len(a["resources"]),
                "_diff": cc - pc,
            }
        )
    out.sort(key=lambda m: -abs(m["_diff"]))
    for m in out:
        m.pop("_diff")
    return out


def _rollup_resources(rows: list[MeterRow], resource_prev: dict[str, int], resource_cur: dict[str, int]) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        a = agg.setdefault(r.resource_key, {"resource_key": r.resource_key, "resource_name": r.resource_name, "prev": ZERO, "cur": ZERO})
        a["prev"] += r.prev_cost
        a["cur"] += r.cur_cost
    out = []
    for k, a in agg.items():
        status = "new" if resource_prev[k] == 0 else "removed" if resource_cur[k] == 0 else "existing"
        out.append(
            {
                "resource_key": k,
                "resource_name": a["resource_name"] or ("(non-resource charges)" if not k else k.rsplit("/", 1)[-1]),
                "status": status,
                "previous_cost": money(a["prev"]),
                "current_cost": money(a["cur"]),
                "difference": money(a["cur"] - a["prev"]),
                "pct_change": money(pct_change(a["prev"], a["cur"])),
                "_d": a["cur"] - a["prev"],
            }
        )
    out.sort(key=lambda x: -abs(x["_d"]))
    for x in out:
        x.pop("_d")
    return out


def _fmt_money(v: Decimal | float | None) -> str:
    if v is None:
        return "n/a"
    v = to_decimal(v)
    sign = "-" if v < 0 else ""
    return f"{sign}{abs(v):,.2f}"


def _fmt_signed(v: Decimal | float) -> str:
    v = to_decimal(v)
    return ("+" if v >= 0 else "-") + f"{abs(v):,.2f}"


def _statements(meters: list[dict], resources: list[dict], totals: dict[str, Decimal], rows: list[MeterRow]):
    facts: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []

    for m in meters[:8]:
        d = to_decimal(m["difference"])
        if d == ZERO:
            continue
        name = " / ".join(x for x in (m["meter_category"], m["meter_subcategory"], m["meter_name"]) if x)
        unit = m["unit"] or "units"
        if m["status"] == "new":
            facts.append({"type": "new_meter", "text": f"Meter '{name}' was billed in the current period but not in the comparison period ({_fmt_signed(d)}).", "impact": money(d)})
        elif m["status"] == "removed":
            facts.append({"type": "removed_meter", "text": f"Meter '{name}' was billed in the comparison period but not in the current period ({_fmt_signed(d)}).", "impact": money(d)})
        else:
            pq, cq = to_decimal(m["previous_quantity"]), to_decimal(m["current_quantity"])
            text = f"'{name}': billed quantity {pq:,.2f} → {cq:,.2f} {unit}"
            if m["quantity_pct"] is not None:
                text += f" ({m['quantity_pct']:+.1f}%)"
            if m["previous_unit_price"] is not None and m["current_unit_price"] is not None:
                if m["unit_price_pct"] is not None and abs(m["unit_price_pct"]) >= 0.5:
                    text += f"; effective unit price {m['previous_unit_price']:,.6f} → {m['current_unit_price']:,.6f} ({m['unit_price_pct']:+.1f}%)"
                else:
                    text += "; effective unit price unchanged"
            text += f". Cost change {_fmt_signed(d)} (volume {_fmt_signed(m['volume_effect'])}, price {_fmt_signed(m['price_effect'])})."
            facts.append({"type": "meter_change", "text": text, "impact": money(d)})

            # Hypotheses derived from units -- always labelled as unverified.
            u = (m["unit"] or "").lower()
            cat = (m["meter_category"] or "").lower()
            mname = (m["meter_name"] or "").lower()
            dq = cq - pq
            if "hour" in u and dq > 0 and to_decimal(m["volume_effect"]) > 0:
                hypotheses.append({
                    "type": "compute_runtime",
                    "text": f"Billed hours for '{m['meter_name']}' rose by {dq:,.1f}. This is consistent with additional instances/nodes or longer runtime. Billing data cannot confirm the cause; verify scaling history (e.g. AKS node pool autoscaler, VMSS instance count) in Azure Activity Log or Azure Monitor.",
                })
            elif ("gb" in u or "tb" in u) and ("transfer" in mname or "bandwidth" in cat or "egress" in mname) and dq > 0:
                hypotheses.append({
                    "type": "network_transfer",
                    "text": f"Data transfer for '{m['meter_name']}' rose by {dq:,.1f} {m['unit']}. Possible causes include higher outbound traffic, cross-region replication or a new integration. Not verifiable from billing data; check network flow logs / Azure Monitor metrics.",
                })
            elif ("gb" in u or "tb" in u) and ("storage" in cat or "month" in u) and dq > 0 and to_decimal(m["volume_effect"]) > 0:
                hypotheses.append({
                    "type": "storage_growth",
                    "text": f"Billed capacity for '{m['meter_name']}' rose by {dq:,.1f} {m['unit']}, consistent with data growth or retention changes. Verify with storage account capacity metrics and lifecycle policies.",
                })
            if m["unit_price_pct"] is not None and abs(m["unit_price_pct"]) >= 2:
                hypotheses.append({
                    "type": "price_change",
                    "text": f"Effective unit price of '{m['meter_name']}' moved {m['unit_price_pct']:+.1f}%. Possible causes: reservation/savings plan coverage change, discount or negotiated price change, or a price update. Confirm against price sheet and commitment utilisation.",
                })

    # Meter swaps on the same resource (removed + new meter in the same category)
    by_res: dict[str, dict[str, list[MeterRow]]] = defaultdict(lambda: {"new": [], "removed": []})
    for r in rows:
        if r.classification == "new_meter":
            by_res[r.resource_key]["new"].append(r)
        elif r.classification == "removed_meter" or (
            r.classification == "volume_price" and r.prev_qty > ZERO and r.cur_qty < r.prev_qty * Decimal("0.5")
        ):
            # a meter that stopped, or collapsed by more than half, while another started
            by_res[r.resource_key]["removed"].append(r)
    for rk, d in by_res.items():
        for n in d["new"]:
            for o in d["removed"]:
                if (n.meter_category or "") == (o.meter_category or "") and n.meter_key != o.meter_key:
                    old_name = " ".join(x for x in (o.meter_subcategory, o.meter_name) if x)
                    new_name = " ".join(x for x in (n.meter_subcategory, n.meter_name) if x)
                    facts.append({
                        "type": "meter_swap",
                        "text": (
                            f"On '{n.resource_name or rk}', meter '{old_name}' "
                            + ("stopped" if o.cur_records == 0 else f"fell {(o.prev_qty - o.cur_qty) / o.prev_qty * 100:.0f}% in billed quantity")
                            + f" and '{new_name}' started in the same category ({n.meter_category})."
                        ),
                        "impact": money(n.cur_cost - o.prev_cost),
                    })
                    hypotheses.append({
                        "type": "sku_change",
                        "text": f"The meter change on '{n.resource_name or rk}' suggests a SKU or tier change. Billing data alone cannot confirm a resize or reconfiguration; check the Azure Activity Log for write operations on this resource.",
                    })

    new_res = [r for r in resources if r["status"] == "new"]
    if new_res:
        total = sum(to_decimal(r["difference"]) for r in new_res)
        names = ", ".join(r["resource_name"] for r in new_res[:5])
        facts.append({"type": "new_resources", "text": f"{len(new_res)} resource(s) had billing records only in the current period ({_fmt_signed(total)}): {names}{'…' if len(new_res) > 5 else ''}.", "impact": money(total)})
    removed_res = [r for r in resources if r["status"] == "removed"]
    if removed_res:
        total = sum(to_decimal(r["difference"]) for r in removed_res)
        facts.append({"type": "removed_resources", "text": f"{len(removed_res)} resource(s) had billing records only in the comparison period ({_fmt_signed(total)}).", "impact": money(total)})
    for key in ("commitment", "credits_refunds", "other_charges"):
        if totals.get(key, ZERO) != ZERO:
            facts.append({"type": key, "text": f"{EFFECT_LABELS[key]}: {_fmt_signed(totals[key])}.", "impact": money(totals[key])})
    return facts, hypotheses
