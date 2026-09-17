"""Direct unit tests for the three pure-Python services behind the Smart
Order Helper's numbers: pricing_service (discount stacking rules),
add_on_service (rule-based add-on quantities + category parsing) and
roof_estimator (house description -> squares). No LLM, no orchestrator."""

import asyncio

import pytest

from app.services import add_on_service, local_data_repository as repo, pricing_service, roof_estimator


def _catalogue():
    products = asyncio.run(repo.get_products()).data["data"]["products"]
    return {p["sku"]: p for p in products}


def _rules():
    return asyncio.run(repo.get_add_on_rules()).data["data"]["rules"]


def _discounts(on_date="2026-09-17"):
    return asyncio.run(repo.get_discounts(on_date=on_date)).data["data"]["discounts"]


def _shingle_line(sku="TL-HDZ-01", squares=10.0, line_no=1):
    p = _catalogue()[sku]
    return {
        "line_no": line_no, "sku": sku, "product": p["productName"], "product_family": p["productFamily"],
        "product_type": p["productType"], "quantity": squares, "unit": "squares",
        "converted_quantity": squares * p["bundlesPerSquare"], "unit_price": p["unitPriceUsd"], "included": True,
    }


# ------------------------------------------------------------ roof_estimator

def test_parse_pitch():
    for text, rise in [("6/12", 6.0), ("8:12", 8.0), ("4 in 12", 4.0), ("steep", 9.0), ("low", 4.0), ("7", 7.0), ("garbage", None), (None, None)]:
        assert roof_estimator.parse_pitch(text) == rise, text


def test_estimate_two_storey_house_with_stated_pitch():
    calc = roof_estimator.estimate(house_sqft=4000, floors=2, pitch="6/12")
    assert calc["status"] == "ok"
    assert calc["footprint_sqft"] == 2000
    assert calc["pitch_factor"] == 1.118
    assert calc["roof_sqft"] == 2236
    assert calc["order_sqft"] == 2460  # x 1.10 waste
    assert calc["squares"] == 25
    assert not any("assumed" in a for a in calc["assumptions"])


def test_estimate_assumes_standard_pitch_and_designer_waste():
    calc = roof_estimator.estimate(house_sqft=2000, floors=1, pitch=None, designer=True)
    assert calc["status"] == "ok"
    assert calc["pitch"] == "6/12"
    assert calc["waste_percent"] == 15
    assert any("assumed a standard 6/12" in a for a in calc["assumptions"])


def test_estimate_needs_input_when_only_land_or_no_floors():
    land = roof_estimator.estimate(house_sqft=None, floors=None, pitch=None, land_sqft=4000)
    assert land["status"] == "needs_input"
    assert "lot doesn't tell us the roof size" in land["questions"][0]

    no_floors = roof_estimator.estimate(house_sqft=3000, floors=None, pitch="6/12")
    assert no_floors["status"] == "needs_input"
    assert "How many storeys" in no_floors["questions"][0]


def test_estimate_with_measured_roof_area_skips_geometry():
    calc = roof_estimator.estimate(house_sqft=None, floors=None, pitch=None, roof_sqft=3000)
    assert calc["method"] == "roof area given"
    assert calc["squares"] == 33  # 3000 * 1.10 = 3300 -> ceil(33)


# ------------------------------------------------------------ add_on_service

def test_requested_categories_reads_full_system_and_named_categories():
    full, named = add_on_service.requested_categories("Quote 65 squares with the full WindProven add-on set")
    assert full is True

    full, named = add_on_service.requested_categories("plus starter, underlayment and the matching ridge cap")
    assert full is False
    assert named == {"Starter strip", "Roof deck protection", "Ridge cap"}

    assert add_on_service.requested_categories("12 squares of HDZ Charcoal") == (False, set())


def test_build_add_on_lines_quantities_follow_the_rules_and_colour_match():
    cat = _catalogue()
    lines, warnings = add_on_service.build_add_on_lines(cat["TL-HDZ-01"], 65, _rules(), cat, include=True)
    by_sku = {l["sku"]: l for l in lines}
    assert by_sku["PRO-START"]["quantity"] == 7      # ceil(65/10)
    assert by_sku["TIGER-PAW"]["quantity"] == 7      # ceil(65/10)
    assert by_sku["WEATHERWATCH"]["quantity"] == 4   # ceil(65/20)
    assert by_sku["SEA-RIDGE-CHAR"]["quantity"] == 22  # ceil(65/3), colour-matched to Charcoal
    assert all(l["included"] and l["source"] == "add_on" for l in lines)
    assert warnings == []


def test_build_add_on_lines_without_ridge_cap_match_warns_and_suggests_only():
    cat = _catalogue()
    lines, warnings = add_on_service.build_add_on_lines(cat["TL-HDZ-04"], 12, _rules(), cat, include=False)
    assert "SEA-RIDGE-CHAR" not in {l["sku"] for l in lines}
    assert any("No colour-matched ridge cap exists for Slate" in w for w in warnings)
    assert all(l["included"] is False for l in lines)
    assert add_on_service.missing_qualifying_categories(lines) == add_on_service.QUALIFYING  # none included


def test_only_categories_limits_what_is_included():
    cat = _catalogue()
    lines, _ = add_on_service.build_add_on_lines(cat["TL-HDZ-01"], 20, _rules(), cat, include=True, only_categories={"Ridge cap", "Starter strip"})
    included = {l["sku"] for l in lines if l["included"]}
    assert included == {"PRO-START", "SEA-RIDGE-CHAR"}
    assert add_on_service.missing_qualifying_categories(lines) == ["Roof deck protection", "Leak barrier"]


# ----------------------------------------------------------- pricing_service

def test_only_the_highest_volume_tier_applies():
    lines = [_shingle_line(squares=101)]
    pricing = pricing_service.price_order(lines, None, _discounts(), 101, None)
    volume = [d for d in pricing["discounts"] if d["kind"] == "volume"]
    assert [d["discount_id"] for d in volume] == ["DSC-VOL-100"]
    assert volume[0]["amount"] == round(101 * 3 * 39.5 * 0.08, 2)
    assert lines[0]["line_subtotal"] == round(101 * 3 * 39.5, 2)
    assert pricing["commission"] is None


def test_only_one_seasonal_promotion_applies_even_when_two_are_active():
    lines = [_shingle_line("TL-HDZ-01", 10, 1), _shingle_line("TL-UHDZ-01", 10, 2)]
    pricing = pricing_service.price_order(lines, None, _discounts("2026-09-17"), 20, None)
    seasonal = [d for d in pricing["discounts"] if d["kind"] == "seasonal"]
    assert [d["discount_id"] for d in seasonal] == ["DSC-SEA-FALL"]  # 4% beats the 2.5% UHDZ launch
    assert seasonal[0]["applies_to_lines"] == [1]


def test_bundle_discount_requires_all_four_categories_included():
    cat = _catalogue()
    shingle = _shingle_line(squares=12)
    add_ons, _ = add_on_service.build_add_on_lines(cat["TL-HDZ-01"], 12, _rules(), cat, include=True, start_line_no=2)
    complete = pricing_service.price_order([shingle, *add_ons], None, _discounts(), 12, None)
    assert "DSC-SYS-COMPLETE" in {d["discount_id"] for d in complete["discounts"]}

    add_ons[0]["included"] = False  # drop the starter strip
    partial = pricing_service.price_order([shingle, *add_ons], None, _discounts(), 12, None)
    assert "DSC-SYS-COMPLETE" not in {d["discount_id"] for d in partial["discounts"]}
    assert partial["included_line_count"] == complete["included_line_count"] - 1


def test_account_discount_and_commission_by_customer_type_and_rep():
    lines = [_shingle_line(squares=10)]
    dist = pricing_service.price_order(lines, {"customerType": "Distributor"}, _discounts("2026-12-01"), 10, {"repId": "REP-002", "name": "Maya Chen", "commissionRate": 0.03})
    assert [d["discount_id"] for d in dist["discounts"]] == ["DSC-ACC-DIST"]
    assert dist["total"] == round(1185.0 * 0.98, 2)
    assert dist["commission"] == {"rep_id": "REP-002", "rep_name": "Maya Chen", "rate": 0.03, "amount": round(dist["total"] * 0.03, 2)}

    contractor = pricing_service.price_order([_shingle_line(squares=10)], {"customerType": "Contractor"}, _discounts("2026-12-01"), 10, None)
    assert contractor["discounts"] == []
    assert contractor["total"] == 1185.0


def test_next_volume_tier_nudge_only_within_ten_squares():
    close = pricing_service.price_order([_shingle_line(squares=55)], None, _discounts(), 55, None)
    assert close["next_volume_tier"]["discount_id"] == "DSC-VOL-60"
    assert close["next_volume_tier"]["squares_short"] == 5
    far = pricing_service.price_order([_shingle_line(squares=10)], None, _discounts(), 10, None)
    assert far["next_volume_tier"] is None
