"""Roof-size estimate for customers who describe a house, not a quantity.

Plain arithmetic the rep can check on a napkin:
  footprint  = living area / storeys
  roof area  = footprint x pitch factor (sqrt(1 + (rise/run)^2))
  order area = roof area x (1 + waste)      (10% waste, 15% for designer shingles)
  squares    = ceil(order area / 100)

Land/lot size is deliberately NOT used as a roof proxy -- a 4,000 sq ft lot
says nothing about the house on it, so the estimator asks for the living
area instead. Every assumption is returned so the rep confirms before an
order is built from it.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

PITCH_WORDS = {"low": 4.0, "shallow": 4.0, "standard": 6.0, "typical": 6.0, "medium": 6.0, "average": 6.0, "steep": 9.0, "very steep": 12.0}
DEFAULT_PITCH = 6.0
WASTE = 0.10
WASTE_DESIGNER = 0.15


def _squares(order_area: float) -> int:
    # Round away binary float noise first: 3000 x 1.10 / 100 is
    # 33.000000000000004 in floating point, which ceil would turn into 34.
    return math.ceil(round(order_area / 100, 6))


def parse_pitch(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    t = str(text).lower().strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:/|:|in|on|over)\s*12", t)
    if m:
        return float(m.group(1))
    for word, rise in PITCH_WORDS.items():
        if word in t:
            return rise
    m = re.fullmatch(r"(\d+(?:\.\d+)?)", t)
    return float(m.group(1)) if m else None


def estimate(
    *,
    house_sqft: Optional[float],
    floors: Optional[float],
    pitch: Optional[str],
    land_sqft: Optional[float] = None,
    roof_sqft: Optional[float] = None,
    designer: bool = False,
) -> dict[str, Any]:
    """Returns {"status": "ok" | "needs_input", ...}."""
    questions: list[str] = []
    assumptions: list[str] = []

    if roof_sqft:
        order_area = roof_sqft * (1 + (WASTE_DESIGNER if designer else WASTE))
        squares = _squares(order_area)
        return {
            "status": "ok", "method": "roof area given", "roof_sqft": round(roof_sqft), "order_sqft": round(order_area),
            "waste_percent": int((WASTE_DESIGNER if designer else WASTE) * 100), "squares": squares,
            "assumptions": [], "inputs": {"roof_sqft": roof_sqft},
        }

    if not house_sqft:
        if land_sqft:
            questions.append(
                f"A {land_sqft:,.0f} sq ft lot doesn't tell us the roof size -- roughly how many sq ft of living space is the house, and how many storeys?"
            )
        else:
            questions.append("Roughly how many sq ft of living space is the house?")
    if house_sqft and not floors:
        questions.append("How many storeys? (a two-storey house has about half the roof footprint of a one-storey house of the same size)")
    if questions:
        return {"status": "needs_input", "questions": questions, "inputs": {"house_sqft": house_sqft, "floors": floors, "pitch": pitch, "land_sqft": land_sqft}}

    rise = parse_pitch(pitch)
    if rise is None:
        rise = DEFAULT_PITCH
        assumptions.append(f"pitch not stated -- assumed a standard {int(DEFAULT_PITCH)}/12")
    factor = math.sqrt(1 + (rise / 12.0) ** 2)
    footprint = float(house_sqft) / float(floors)
    roof_area = footprint * factor
    waste = WASTE_DESIGNER if designer else WASTE
    order_area = roof_area * (1 + waste)
    squares = _squares(order_area)
    assumptions.append(f"footprint = {house_sqft:,.0f} sq ft / {floors:g} storey(s) = {footprint:,.0f} sq ft")
    assumptions.append(f"pitch factor for {rise:g}/12 = {factor:.3f}")
    assumptions.append(f"{int(waste * 100)}% waste allowance")
    return {
        "status": "ok",
        "method": "living area x storeys x pitch",
        "footprint_sqft": round(footprint),
        "pitch": f"{rise:g}/12",
        "pitch_factor": round(factor, 3),
        "roof_sqft": round(roof_area),
        "waste_percent": int(waste * 100),
        "order_sqft": round(order_area),
        "squares": squares,
        "assumptions": assumptions,
        "inputs": {"house_sqft": house_sqft, "floors": floors, "pitch": pitch, "land_sqft": land_sqft},
    }
