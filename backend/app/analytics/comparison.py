"""Centralised cost comparison engine.

Every screen that compares two periods goes through these functions so formulas and
edge-case behaviour are identical everywhere:

    difference        = current - previous
    percentage change = (current - previous) / |previous| * 100      (None when previous == 0)

Using |previous| keeps the sign of the percentage aligned with the direction of the
change when the previous value is negative (net credits / refunds). A percentage is never
infinite: when previous is zero the change is classified (new / unchanged) instead.

All arithmetic uses ``Decimal``; rounding happens only when values are serialised.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

ZERO = Decimal("0")
HUNDRED = Decimal("100")

ChangeStatus = Literal["new", "removed", "increased", "decreased", "unchanged", "no_data"]
SortKey = Literal["abs_diff", "pct_increase", "largest_decrease", "current_cost", "previous_cost", "contribution", "largest_increase", "name"]


def to_decimal(value: Any) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def pct_change(previous: Decimal, current: Decimal) -> Decimal | None:
    previous, current = to_decimal(previous), to_decimal(current)
    if previous == ZERO:
        return None
    return (current - previous) / abs(previous) * HUNDRED


def safe_ratio_pct(part: Decimal, whole: Decimal) -> Decimal | None:
    whole = to_decimal(whole)
    if whole == ZERO:
        return None
    return to_decimal(part) / whole * HUNDRED


def classify_change(
    previous: Decimal,
    current: Decimal,
    previous_records: int | None = None,
    current_records: int | None = None,
) -> ChangeStatus:
    """Classify a change. Record counts (when known) distinguish a *new* item -- one with
    no billing records at all in the comparison period -- from an item whose cost simply
    rose from zero (e.g. a free-tier resource)."""
    previous, current = to_decimal(previous), to_decimal(current)
    if previous_records is not None and current_records is not None:
        if previous_records == 0 and current_records == 0:
            return "no_data"
        if previous_records == 0:
            return "new"
        if current_records == 0:
            return "removed"
    elif previous == ZERO and current != ZERO:
        return "new"
    elif current == ZERO and previous != ZERO:
        return "removed"
    diff = current - previous
    if diff > ZERO:
        return "increased"
    if diff < ZERO:
        return "decreased"
    return "unchanged"


@dataclass
class ComparedItem:
    key: str
    label: str
    previous: Decimal = ZERO
    current: Decimal = ZERO
    previous_records: int | None = None
    current_records: int | None = None
    previous_quantity: Decimal | None = None
    current_quantity: Decimal | None = None
    unit: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    # derived (filled by ``compute_metrics``)
    diff: Decimal = ZERO
    pct: Decimal | None = None
    status: ChangeStatus = "unchanged"
    share_of_total: Decimal | None = None
    contribution_pct: Decimal | None = None
    quantity_diff: Decimal | None = None
    quantity_pct: Decimal | None = None
    previous_daily_avg: Decimal | None = None
    current_daily_avg: Decimal | None = None


@dataclass
class ComparisonTotals:
    previous: Decimal
    current: Decimal
    diff: Decimal
    pct: Decimal | None
    previous_days: int | None
    current_days: int
    previous_daily_avg: Decimal | None
    current_daily_avg: Decimal
    run_rate: Decimal | None  # projected full-period cost when the current period is incomplete
    status: ChangeStatus


def compute_totals(
    previous: Decimal | None,
    current: Decimal,
    *,
    current_days: int,
    previous_days: int | None,
    nominal_days: int | None = None,
) -> ComparisonTotals:
    current = to_decimal(current)
    prev = to_decimal(previous) if previous is not None else None
    cur_avg = current / Decimal(current_days) if current_days else ZERO
    prev_avg = (prev / Decimal(previous_days)) if (prev is not None and previous_days) else None
    run_rate = cur_avg * Decimal(nominal_days) if nominal_days and nominal_days > current_days else None
    if prev is None:
        return ComparisonTotals(ZERO, current, ZERO, None, None, current_days, None, cur_avg, run_rate, "unchanged")
    return ComparisonTotals(
        previous=prev,
        current=current,
        diff=current - prev,
        pct=pct_change(prev, current),
        previous_days=previous_days,
        current_days=current_days,
        previous_daily_avg=prev_avg,
        current_daily_avg=cur_avg,
        run_rate=run_rate,
        status=classify_change(prev, current),
    )


def compute_metrics(
    items: list[ComparedItem],
    *,
    current_days: int | None = None,
    previous_days: int | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Fill derived fields in place. Returns (total_previous, total_current, total_diff)."""
    total_prev = sum((i.previous for i in items), ZERO)
    total_cur = sum((i.current for i in items), ZERO)
    total_diff = total_cur - total_prev
    for i in items:
        i.diff = i.current - i.previous
        i.pct = pct_change(i.previous, i.current)
        i.status = classify_change(i.previous, i.current, i.previous_records, i.current_records)
        i.share_of_total = safe_ratio_pct(i.current, total_cur)
        i.contribution_pct = safe_ratio_pct(i.diff, total_diff)
        if i.previous_quantity is not None or i.current_quantity is not None:
            pq, cq = to_decimal(i.previous_quantity), to_decimal(i.current_quantity)
            i.quantity_diff = cq - pq
            i.quantity_pct = pct_change(pq, cq)
        if current_days:
            i.current_daily_avg = i.current / Decimal(current_days)
        if previous_days:
            i.previous_daily_avg = i.previous / Decimal(previous_days)
    return total_prev, total_cur, total_diff


def sort_items(items: list[ComparedItem], sort: str = "abs_diff") -> list[ComparedItem]:
    """Sort comparison rows.

    The default ranks by *absolute* financial movement: a 500% increase on a $2 resource
    never outranks a $10,000 increase. Percentage sorts push rows without a defined
    percentage (new items) after all rows that have one, then rank by absolute change.
    """
    if sort == "abs_diff":
        return sorted(items, key=lambda i: (-abs(i.diff), -abs(i.current), i.label))
    if sort in ("largest_increase",):
        return sorted(items, key=lambda i: (-i.diff, i.label))
    if sort == "largest_decrease":
        return sorted(items, key=lambda i: (i.diff, i.label))
    if sort == "current_cost":
        return sorted(items, key=lambda i: (-i.current, i.label))
    if sort == "previous_cost":
        return sorted(items, key=lambda i: (-i.previous, i.label))
    if sort == "name":
        return sorted(items, key=lambda i: (i.label.lower(), i.key))
    if sort == "contribution":
        return sorted(items, key=lambda i: (-(i.contribution_pct if i.contribution_pct is not None else Decimal("-1e30")), i.label))
    if sort == "pct_increase":
        return sorted(
            items,
            key=lambda i: (
                0 if i.pct is not None else 1,
                -(i.pct if i.pct is not None else ZERO),
                -abs(i.diff),
                i.label,
            ),
        )
    raise ValueError(f"Unknown sort '{sort}'")


# ---------------------------------------------------------------------------------------
# waterfall attribution
# ---------------------------------------------------------------------------------------

@dataclass
class WaterfallStep:
    key: str
    label: str
    value: Decimal  # signed contribution
    start: Decimal  # running total before this step
    end: Decimal  # running total after this step
    kind: Literal["start", "increase", "decrease", "end", "other"]
    previous: Decimal | None = None
    current: Decimal | None = None
    pct: Decimal | None = None
    status: str | None = None
    member_count: int | None = None


@dataclass
class Waterfall:
    previous_total: Decimal
    current_total: Decimal
    net_change: Decimal
    steps: list[WaterfallStep]
    reconciled: bool
    reconciliation_difference: Decimal
    top_n: int
    other_member_count: int


def build_waterfall(items: Iterable[ComparedItem], previous_total: Decimal, current_total: Decimal, top_n: int = 5) -> Waterfall:
    """Explain the movement from ``previous_total`` to ``current_total``.

    The ``top_n`` items with the largest absolute change are shown individually; all
    remaining items are combined into an "Other" step equal to the exact residual, so the
    chart always reconciles: start + sum(steps) == end.
    """
    previous_total, current_total = to_decimal(previous_total), to_decimal(current_total)
    ranked = sort_items([i for i in items], "abs_diff")
    top_n = max(0, top_n)
    shown = [i for i in ranked[:top_n] if i.diff != ZERO]
    shown_ids = {id(i) for i in shown}
    rest = [i for i in ranked if id(i) not in shown_ids]
    net = current_total - previous_total

    steps: list[WaterfallStep] = [
        WaterfallStep("__start__", "Previous period", previous_total, ZERO, previous_total, "start", previous=previous_total)
    ]
    running = previous_total
    for i in shown:
        steps.append(
            WaterfallStep(
                key=i.key,
                label=i.label,
                value=i.diff,
                start=running,
                end=running + i.diff,
                kind="increase" if i.diff > ZERO else "decrease",
                previous=i.previous,
                current=i.current,
                pct=i.pct,
                status=i.status,
            )
        )
        running += i.diff
    residual = net - sum((i.diff for i in shown), ZERO)
    rest_prev = sum((i.previous for i in rest), ZERO)
    rest_cur = sum((i.current for i in rest), ZERO)
    if rest and (residual != ZERO or rest_prev != ZERO or rest_cur != ZERO):
        steps.append(
            WaterfallStep(
                key="__other__",
                label=f"Other ({len(rest)})",
                value=residual,
                start=running,
                end=running + residual,
                kind="other",
                previous=rest_prev,
                current=rest_cur,
                pct=pct_change(rest_prev, rest_cur),
                member_count=len(rest),
            )
        )
        running += residual
    steps.append(WaterfallStep("__end__", "Current period", current_total, ZERO, current_total, "end", current=current_total))
    difference = running - current_total
    return Waterfall(
        previous_total=previous_total,
        current_total=current_total,
        net_change=net,
        steps=steps,
        reconciled=difference == ZERO,
        reconciliation_difference=difference,
        top_n=top_n,
        other_member_count=len(rest),
    )


# ---------------------------------------------------------------------------------------
# serialisation helpers
# ---------------------------------------------------------------------------------------

def money(value: Decimal | None, places: int = 2) -> float | None:
    if value is None:
        return None
    q = Decimal(1).scaleb(-places)
    out = float(to_decimal(value).quantize(q, rounding=ROUND_HALF_UP))
    return 0.0 if out == 0 else out  # never emit negative zero


def pct_out(value: Decimal | None) -> float | None:
    return money(value, 2)


def qty(value: Decimal | None) -> float | None:
    return money(value, 4)


def price(value: Decimal | None) -> float | None:
    return money(value, 6)
