"""Envelope tests for the shared catalogue (gaf_catalog.GafCatalog) as served
through local_data_repository against the REAL synthetic dataset under
data/. No network, no Azure: this only ever reads data/*.json off disk.
Every orchestrator reads exactly these envelopes."""

import asyncio

from app.services import local_data_repository as repo
from app.services.gaf_catalog import GafCatalog


def _data(coro, key):
    result = asyncio.run(coro)
    assert result.success, result
    return result.data["data"][key]


# --------------------------------------------------------------- products

def test_products_catalogue_shape_and_filters():
    products = _data(repo.get_products(), "products")
    assert len(products) == 24
    hdz = _data(repo.get_products(sku="tl-hdz-01"), "products")[0]
    assert hdz["productName"] == "Timberline HDZ Shingles"
    assert hdz["colour"] == "Charcoal"
    assert hdz["bundlesPerSquare"] == 3
    assert hdz["unitPriceUsd"] == 39.5
    assert hdz["pricePerSquareUsd"] == 118.5
    assert hdz["ridgeCapMatch"] == "SEA-RIDGE-CHAR"
    assert hdz["largeOrderDeliveryCheck"]["thresholdSquares"] == 30
    assert len(_data(repo.get_products(family="Timberline HDZ"), "products")) == 8
    assert {p["sku"] for p in _data(repo.get_products(product_type="Ridge cap"), "products")} == {"SEA-RIDGE-CHAR", "SEA-RIDGE-WEA", "TIMBERTEX-CHAR"}
    assert _data(repo.get_products(sku="TL-HDZ-03"), "products")[0]["ridgeCapMatch"] is None


def test_unknown_sku_is_a_not_found_tool_result_not_an_exception():
    result = asyncio.run(repo.get_products(sku="TL-HDZ-CHAR"))
    assert result.success is False
    assert result.error == "gaf_api_not_found"
    assert result.status_code == 404
    assert "Unknown sku" in result.data["supportMessage"]


# -------------------------------------------------------------- customers

def test_customers_by_account_id_and_exact_alias():
    c = _data(repo.get_customers(account_id=" acc-1001 "), "customers")[0]
    assert c["customerName"] == "Tampa Contractor Group 01"
    assert c["tradeName"] == "Sunshine Roofing Supply"
    assert c["creditHold"] is False and c["availableCredit"] == 65000.0
    assert c["salesRepId"] == "REP-001" and c["homeWarehouseId"] == "DC-FL-TAM"
    assert [x["accountId"] for x in _data(repo.get_customers(name="Sunshine Roofing"), "customers")] == ["ACC-1001"]
    assert [x["accountId"] for x in _data(repo.get_customers(name="gulf coast"), "customers")] == ["ACC-1002"]


def test_exact_name_wins_but_a_partial_name_surfaces_the_ambiguity():
    assert [x["accountId"] for x in _data(repo.get_customers(name="Tampa Contractor Group 01"), "customers")] == ["ACC-1001"]
    assert {x["accountId"] for x in _data(repo.get_customers(name="Tampa Contractor"), "customers")} == {"ACC-1001", "ACC-1013"}
    unknown = asyncio.run(repo.get_customers(name="Totally Fictional Roofing Co"))
    assert unknown.success is False and unknown.error == "gaf_api_not_found"
    assert len(_data(repo.get_customers(rep_id="REP-002"), "customers")) == 4
    assert _data(repo.get_customers(account_id="ACC-1004"), "customers")[0]["creditHold"] is True


# -------------------------------------------------------------- inventory

def test_inventory_requires_a_sku_or_warehouse():
    result = asyncio.run(repo.get_inventory())
    assert result.success is False
    assert result.error == "gaf_api_bad_request"
    assert result.status_code == 400
    rows = _data(repo.get_inventory(sku="TL-HDZ-01"), "inventory")
    assert {r["warehouseId"] for r in rows} == {"DC-FL-TAM", "DC-FL-MIA", "DC-GA-ATL", "DC-TX-DAL", "DC-NJ-NEW", "DC-NC-CHA"}
    tampa = next(r for r in rows if r["warehouseId"] == "DC-FL-TAM")
    assert tampa["quantityAvailable"] == 313 and tampa["unit"] == "bundles" and tampa["warehouse"] == "Tampa DC"
    assert len(_data(repo.get_inventory(warehouse_id="DC-NC-CHA"), "inventory")) == 24
    assert _data(repo.get_inventory(sku="NOT-A-SKU"), "inventory") == []


# ----------------------------------------------------------------- orders

def test_orders_by_id_account_status_and_rep():
    order = _data(repo.get_orders(order_id="ORD-77009"), "orders")[0]
    assert order["accountId"] == "ACC-1009" and order["status"] == "Delivered"
    assert order["lines"][0]["sku"] == "TL-UHDZ-01" and order["lines"][0]["quantity"] == 120
    assert order["totalUsd"] is not None
    assert len(_data(repo.get_orders(), "orders")) == 45
    drafts = _data(repo.get_orders(account_id="ACC-1005", status="draft"), "orders")
    assert [o["orderId"] for o in drafts] == ["ORD-77005"]
    assert all(o["salesRepId"] == "REP-004" for o in _data(repo.get_orders(rep_id="REP-004"), "orders"))


# -------------------------------------------------------------- documents

def test_documents_include_content_and_passages_and_flag_expiry():
    docs = {d["docId"]: d for d in _data(repo.get_documents(), "documents")}
    assert docs["DOC-OLD"]["status"] == "expired"
    assert docs["DOC-102"]["status"] == "active"
    assert docs["DOC-102"]["content"].startswith("Document ID: DOC-102")
    assert {p["passageId"] for p in docs["DOC-102"]["passages"]} == {"P-003", "P-105", "P-106"}
    lean = _data(repo.get_documents(doc_id="DOC-101", include_content=False), "documents")[0]
    assert "content" not in lean and "passages" not in lean
    assert asyncio.run(repo.get_documents(doc_id="DOC-999")).success is False


def test_kb_passages_query_scores_and_hides_expired_docs():
    hits = _data(repo.get_kb_passages(query="what do I need for the strongest warranty add-on categories"), "passages")
    assert hits and hits[0]["matchScore"] >= hits[-1]["matchScore"]
    assert hits[0]["docId"] == "DOC-102"
    assert all("DOC-OLD" != p["docId"] for p in _data(repo.get_kb_passages(query="obsolete example never retrieved when expired"), "passages"))
    assert {p["docId"] for p in _data(repo.get_kb_passages(intent="HDZ-APPROVAL"), "passages")} == {"DOC-101"}
    assert GafCatalog(repo.catalog.data_dir).kb_passages(active_only=False, doc_id="DOC-OLD")["passages"][0]["passageId"] == "P-007"


def test_product_approval_and_warranty_rules():
    hdz = asyncio.run(repo.get_product_approval("Timberline HDZ")).data["data"]
    assert hdz["floridaApproval"] == "FL-16254.3" and hdz["miamiDadeNoa"] == "NOA 22-0518.09"
    assert asyncio.run(repo.get_product_approval("Timberline UHDZ")).data["data"]["floridaApproval"] == "FL-18820.1"
    assert asyncio.run(repo.get_product_approval("Timberline")).success is False  # ambiguous, never merged
    assert asyncio.run(repo.get_product_approval("Camelot II")).success is False
    tiers = {t["tier"]: t for t in _data(repo.get_warranty_rules(), "tiers")}
    assert tiers["WindProven"]["addOnsRequired"] == ["Leak barrier", "Roof deck protection", "Starter strip", "Ridge cap"]
    assert any("leak" in r["topic"].lower() for r in _data(repo.get_escalation_rules(), "rules"))


# ------------------------------------------------------------ contractors

def test_contractors_by_zip_sorted_by_distance_with_radius_and_tier():
    data = asyncio.run(repo.get_contractors(zip_code="30061", limit=8)).data["data"]
    assert data["location"]["city"] == "Marietta" and data["location"]["county"] == "Cobb"
    dists = [c["distanceMiles"] for c in data["contractors"]]
    assert dists == sorted(dists) and all(d <= 25 for d in dists) and len(dists) == 8
    elite = asyncio.run(repo.get_contractors(zip_code="30061", min_tier="master_elite")).data["data"]["contractors"]
    assert elite and all(c["certificationTier"] in ("master_elite", "presidents_club") for c in elite)
    tight = asyncio.run(repo.get_contractors(zip_code="30061", radius_miles=1)).data["data"]
    assert tight["radiusExpanded"] is True and tight["contractors"]
    by_city = asyncio.run(repo.get_contractors(city="Charlotte")).data["data"]
    assert by_city["location"]["zip"] == "28202"
    bad = asyncio.run(repo.get_contractors(zip_code="99999"))
    assert bad.success is False and bad.error == "gaf_api_not_found"
    assert asyncio.run(repo.get_contractors()).error == "gaf_api_bad_request"


# -------------------------------------------------------------- discounts

def test_discounts_on_a_fixed_date():
    fall = {d["discountId"] for d in _data(repo.get_discounts(on_date="2026-09-17"), "discounts")}
    assert {"DSC-VOL-30", "DSC-VOL-60", "DSC-VOL-100", "DSC-SEA-FALL", "DSC-SEA-UHDZ", "DSC-SYS-COMPLETE", "DSC-ACC-DIST"} == fall
    winter = {d["discountId"] for d in _data(repo.get_discounts(on_date="2026-12-01"), "discounts")}
    assert "DSC-SEA-FALL" not in winter and "DSC-SEA-WINTER" in winter
    complete = next(d for d in _data(repo.get_discounts(on_date="2026-12-01"), "discounts") if d["discountId"] == "DSC-SYS-COMPLETE")
    assert complete["requiresCategories"] == ["Starter strip", "Roof deck protection", "Leak barrier", "Ridge cap"]


# ------------------------------------------------- reps / emails / use cases

def test_sales_reps_emails_and_use_cases():
    reps = _data(repo.get_sales_reps(), "salesReps")
    assert [r["repId"] for r in reps] == ["REP-001", "REP-002", "REP-003", "REP-004"]
    rep = _data(repo.get_sales_reps(rep_id="rep-001"), "salesReps")[0]
    assert rep["name"] == "Jordan Reyes" and rep["commissionRate"] == 0.03 and "ACC-1001" in rep["accounts"]
    assert asyncio.run(repo.get_sales_reps(rep_id="REP-999")).success is False

    inbox = _data(repo.get_emails(rep_id="REP-001"), "emails")
    assert {e["emailId"] for e in inbox} == {"EML-001", "EML-005", "EML-007", "EML-010"}
    assert _data(repo.get_emails(email_id="EML-001"), "emails")[0]["tradeName"] == "Sunshine Roofing Supply"
    assert asyncio.run(repo.get_emails(email_id="EML-999")).success is False

    uc = asyncio.run(repo.get_use_cases()).data["data"]
    assert {u["id"] for u in uc["useCases"]} >= {"UC-01", "UC-08", "UC-13", "UC-14"}
    assert uc["orderScenarios"][0]["scenario_id"] == "OS-001"
    assert len(uc["advisorScenarios"]) == 28
