"""Deterministic pricing for an order: unit price x base quantity per line,
automatic discounts from the catalogue's discounts table, and the rep's
commission. No model call anywhere near a dollar figure.

Discount rules (see data/discounts.json and DOC-110):
  volume   -- highest qualifying tier only, on the lines it applies to
  seasonal -- highest-percent active promotion only (they never stack with
              each other), on matching families/types
  bundle   -- requires every listed category to be on the order (included)
  account  -- customer-type allowance on the whole order
Every applied discount becomes its own line so the rep can see exactly
why the total moved.
"""

from __future__ import annotations

from typing import Any, Optional


def _applies(discount: dict[str, Any], line: dict[str, Any]) -> bool:
    a = discount.get("appliesTo") or {}
    if a.get("skus") and line["sku"] not in a["skus"]:
        return False
    if a.get("productFamilies") and line.get("product_family") not in a["productFamilies"]:
        return False
    if a.get("productTypes") and line.get("product_type") not in a["productTypes"]:
        return False
    if not (a.get("skus") or a.get("productFamilies") or a.get("productTypes")):
        return True
    return True


def price_lines(lines: list[dict[str, Any]]) -> None:
    """Fills unit_price / line_subtotal on every line in place."""
    for line in lines:
        unit_price = float(line.get("unit_price") or 0.0)
        qty = float(line.get("converted_quantity") or line.get("quantity") or 0.0)
        line["line_subtotal"] = round(unit_price * qty, 2)


def price_order(
    lines: list[dict[str, Any]],
    customer: Optional[dict[str, Any]],
    discounts: list[dict[str, Any]],
    total_squares: float,
    rep: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    price_lines(lines)
    included = [l for l in lines if l.get("included", True)]
    subtotal = round(sum(l["line_subtotal"] for l in included), 2)

    applied: list[dict[str, Any]] = []

    def add(discount: dict[str, Any], targets: list[dict[str, Any]], scope_note: str) -> None:
        base = sum(l["line_subtotal"] for l in targets)
        if base <= 0:
            return
        amount = round(base * float(discount["percent"]) / 100.0, 2)
        if amount <= 0:
            return
        applied.append({
            "discount_id": discount["discountId"], "name": discount["name"], "kind": discount["kind"],
            "percent": discount["percent"], "amount": amount, "badge": discount.get("badge"),
            "applies_to_lines": [l["line_no"] for l in targets], "note": scope_note,
            "description": discount.get("description"),
        })

    # volume: the single highest tier the order qualifies for
    volume = [d for d in discounts if d["kind"] == "volume" and d.get("minSquares") is not None and total_squares >= d["minSquares"]]
    if volume:
        best = max(volume, key=lambda d: d["percent"])
        add(best, [l for l in included if _applies(best, l)], f"{total_squares:g} squares qualifies for the {best['minSquares']}+ tier")

    # seasonal: one promotion only, the best that matches something on the order
    seasonal = []
    for d in discounts:
        if d["kind"] != "seasonal":
            continue
        targets = [l for l in included if _applies(d, l)]
        if targets:
            seasonal.append((d, targets))
    if seasonal:
        d, targets = max(seasonal, key=lambda x: x[0]["percent"])
        add(d, targets, f"active {d['validFrom']} to {d['validTo']}")

    # bundle: all required categories present among included lines
    categories = {l.get("product_type") for l in included}
    for d in discounts:
        if d["kind"] != "bundle":
            continue
        required = set(d.get("requiresCategories") or [])
        if required and required.issubset(categories):
            add(d, [l for l in included if _applies(d, l)], "all four WindProven add-on categories are on the order")

    # account: customer-type allowance on the whole order
    ctype = (customer or {}).get("customerType")
    for d in discounts:
        if d["kind"] == "account" and ctype and ctype in (d.get("appliesTo") or {}).get("customerTypes", []):
            add(d, included, f"{ctype} account")

    discount_total = round(sum(d["amount"] for d in applied), 2)
    total = round(subtotal - discount_total, 2)

    commission = None
    if rep:
        rate = float(rep.get("commissionRate") or 0)
        commission = {"rep_id": rep.get("repId"), "rep_name": rep.get("name"), "rate": rate, "amount": round(total * rate, 2)}

    # Discounts the order is close to but did not reach -- a nudge for the rep.
    next_tier = None
    for d in sorted((d for d in discounts if d["kind"] == "volume" and d.get("minSquares")), key=lambda d: d["minSquares"]):
        if total_squares < d["minSquares"]:
            gap = d["minSquares"] - total_squares
            if gap <= 10:
                next_tier = {"discount_id": d["discountId"], "name": d["name"], "percent": d["percent"], "squares_short": round(gap, 2)}
            break

    return {
        "currency": "USD",
        "subtotal": subtotal,
        "discounts": applied,
        "discount_total": discount_total,
        "total": total,
        "commission": commission,
        "next_volume_tier": next_tier,
        "included_line_count": len(included),
    }
