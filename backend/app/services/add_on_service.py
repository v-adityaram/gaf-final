"""Turns the catalogue's add-on rules into concrete, priced add-on lines
for a shingle order -- deterministic quantity arithmetic, never a model.

Quantities come straight from add_on_rules.json ("1 bundle per 10
squares" -> ceil(squares / 10)). The colour-matched ridge cap uses the
shingle's own ridgeCapMatch; when there is none (only Charcoal and
Weathered Wood ridge caps exist in the prototype), the ridge line is
still proposed but flagged so the rep confirms the colour with the
customer instead of the assistant guessing.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

CATEGORY_ALIASES = {
    "starter strip": ["starter", "starter strip", "pro-start", "prostart", "weatherblocker"],
    "roof deck protection": ["deck protection", "roof deck", "underlayment", "tiger paw", "deck-armor", "deck armor"],
    "leak barrier": ["leak barrier", "ice and water", "weatherwatch", "stormguard"],
    "ridge cap": ["ridge cap", "ridge", "seal-a-ridge", "timbertex", "hip and ridge"],
    "attic ventilation": ["vent", "ventilation", "cobra", "ridge vent"],
}
FULL_SYSTEM_PATTERN = re.compile(
    r"\b(add[- ]?ons?|accessor\w*|complete system|full system|whole system|wind ?proven|top(?: wind)? warranty|strongest(?: wind)? warranty|best(?: wind)? warranty|everything (?:it|we) needs?)\b",
    re.IGNORECASE,
)
QUALIFYING = ["Starter strip", "Roof deck protection", "Leak barrier", "Ridge cap"]


def category_for(text: str) -> Optional[str]:
    """The add-on category a bare product mention belongs to ("starter",
    "underlayment", "matching ridge cap"), or None for a real product line
    (a named shingle, or an add-on with its own quantity is kept as a line)."""
    t = (text or "").lower().strip()
    if not t or "shingle" in t or "timberline" in t or "camelot" in t or "hdz" in t:
        return None
    for category, aliases in CATEGORY_ALIASES.items():
        if any(a in t for a in aliases):
            return category[0].upper() + category[1:]
    return None


def requested_categories(text: str) -> tuple[bool, set[str]]:
    """(wants_full_system, explicitly named categories) read from the
    customer's words."""
    t = (text or "").lower()
    full = bool(FULL_SYSTEM_PATTERN.search(t))
    named: set[str] = set()
    for category, aliases in CATEGORY_ALIASES.items():
        if any(a in t for a in aliases):
            named.add(category.capitalize() if category != "roof deck protection" else "Roof deck protection")
    named = {c[0].upper() + c[1:] for c in named}
    return full, named


def _rule_quantity(rule: dict[str, Any], squares: float, ridge_feet: Optional[float]) -> Optional[int]:
    if rule.get("perSquares"):
        return max(1, math.ceil(squares / rule["perSquares"]) * (rule.get("qtyPer") or 1))
    if rule.get("perRidgeFeet"):
        feet = ridge_feet if ridge_feet else squares * 1.2  # prototype heuristic: ~1.2 ridge ft per square
        return max(1, math.ceil(feet / rule["perRidgeFeet"]) * (rule.get("qtyPer") or 1))
    return None


def build_add_on_lines(
    primary_product: dict[str, Any],
    squares: float,
    rules: list[dict[str, Any]],
    catalogue: dict[str, dict[str, Any]],
    *,
    include: bool,
    only_categories: Optional[set[str]] = None,
    start_line_no: int = 2,
    ridge_feet: Optional[float] = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Returns (lines, warnings). Lines carry included=True when the
    customer asked for add-ons (or the specific category), else they are
    suggestions the rep can tick on the form."""
    lines: list[dict[str, Any]] = []
    warnings: list[str] = []
    family = primary_product.get("productFamily") or ""
    colour = primary_product.get("colour") or ""
    line_no = start_line_no
    seen_types: set[str] = set()

    for rule in sorted(rules, key=lambda r: (r["priority"], r["ruleId"])):
        trig = rule["trigger"].lower()
        rtype = rule["recommendationType"]
        if rtype in seen_types:
            continue  # AR-004/AR-005 are both "Ridge cap"; one colour-matched line is enough
        sku = rule.get("suggestedSku")
        if rtype == "Ridge cap":
            sku = primary_product.get("ridgeCapMatch")
            family_ok = True
        else:
            family_ok = ("any" in trig) or (family.lower() in trig) or ("shingle" in trig and "hdz" not in trig)
            if "timberline hdz" in trig and family != "Timberline HDZ":
                family_ok = False
        if not family_ok or not sku:
            if rtype == "Ridge cap" and not sku:
                seen_types.add(rtype)
                warnings.append(
                    f"No colour-matched ridge cap exists for {colour or 'this colour'} in the catalogue -- confirm the ridge cap colour with the customer (Seal-A-Ridge comes in Charcoal or Weathered Wood)."
                )
            continue
        product = catalogue.get(sku)
        if not product:
            continue
        qty = _rule_quantity(rule, squares, ridge_feet)
        if not qty:
            continue
        category = product["productType"]
        seen_types.add(rtype)
        wanted = include and (only_categories is None or category in only_categories)
        lines.append({
            "line_no": line_no,
            "sku": sku,
            "product": product["productName"],
            "colour": product.get("colour"),
            "product_family": product.get("productFamily"),
            "product_type": category,
            "quantity": qty,
            "unit": product["soldIn"].lower() + "s",
            "converted_quantity": qty,
            "converted_unit": product["soldIn"].lower() + "s",
            "conversion_note": f"{rule['quantityLogic']} -> {qty} for {squares:g} squares",
            "unit_price": product["unitPriceUsd"],
            "price_unit": product["soldIn"],
            "source": "add_on",
            "included": wanted,
            "add_on_rule": rule["ruleId"],
            "rationale": rule["rationale"],
            "qualifying": category in QUALIFYING,
            "swatch_hex": product.get("swatchHex"),
            "badges": product.get("badges", []),
            "image_url": product.get("imageUrl"),
        })
        line_no += 1
    return lines, warnings


def missing_qualifying_categories(lines: list[dict[str, Any]]) -> list[str]:
    present = {l.get("product_type") for l in lines if l.get("included", True)}
    return [c for c in QUALIFYING if c not in present]
