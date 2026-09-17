#!/usr/bin/env python
"""Validates the synthetic demo dataset under data/ for internal
consistency: no orphan references between files, arithmetic that adds up,
and every demo use case backed by real records.

Run: python scripts/validate_demo_data.py   (from anywhere -- paths resolve
relative to this file). Exits 0 and prints "ALL CHECKS PASSED" or exits 1
and lists every problem. Pure stdlib; only reads data/ off disk.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

errors: list[str] = []


def load(name: str):
    path = DATA_DIR / name
    if not path.exists():
        errors.append(f"MISSING FILE: {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    products = load("products.json")
    customers = load("customers.json")
    inventory = load("inventory.json")
    orders = load("orders.json")
    warehouses = load("warehouses.json")
    documents = load("documents.json")
    passages = load("kb_passages.json")
    rules = load("add_on_rules.json")
    discounts = load("discounts.json")
    contractors = load("contractors.json")
    zips = load("zips.json")
    counties = load("counties.json")
    reps = load("sales_reps.json")
    emails = load("emails.json")
    approvals = load("product_approval.json")
    warranty_rules = load("warranty_rules.json")
    use_cases = load("demo_scenarios/use_cases.json") or {}

    skus = {p["sku"] for p in products}
    accounts = {c["customer_id"] for c in customers}
    wh_ids = {w["warehouse_id"] for w in warehouses}
    doc_ids = {d["document_id"] for d in documents}
    zip_codes = {z["zip"] for z in zips}
    region_ids = {c["region_id"] for c in counties}
    rep_ids = {r["rep_id"] for r in reps}
    families = {p["product_family"] for p in products}

    check(len(skus) == len(products), "products.json: duplicate SKUs")
    for p in products:
        check(p["unit_price_usd"] > 0, f"{p['sku']}: unit price must be positive")
        check(p["coverage_sqft_per_unit"] > 0, f"{p['sku']}: coverage must be positive")
        for sku in p.get("recommended_add_ons", []):
            check(sku in skus, f"{p['sku']}: recommended add-on {sku} not in catalogue")
        if p.get("ridge_cap_match"):
            check(p["ridge_cap_match"] in skus, f"{p['sku']}: ridge cap match {p['ridge_cap_match']} not in catalogue")
        if p["category"] == "Main shingle":
            check(p["bundles_per_square"] > 0, f"{p['sku']}: main shingle needs bundles_per_square")
            check(p.get("swatch_hex"), f"{p['sku']}: main shingle needs a swatch")

    for r in rules:
        if r.get("suggested_sku"):
            check(r["suggested_sku"] in skus, f"{r['rule_id']}: suggested SKU {r['suggested_sku']} not in catalogue")
        if r.get("per_squares") or r.get("per_ridge_feet"):
            check(r.get("qty_per"), f"{r['rule_id']}: parsed quantity logic missing qty_per")

    for c in customers:
        check(c["credit_limit"] > 0, f"{c['customer_id']}: credit limit must be positive")
        check(abs((c["credit_limit"] - c["current_balance"]) - c["available_credit"]) < 0.01, f"{c['customer_id']}: available credit does not add up")
        check(c["credit_hold"] == (c["credit_status"] == "CREDIT HOLD"), f"{c['customer_id']}: credit_hold flag disagrees with credit_status")
        check(c["home_warehouse_id"] in wh_ids, f"{c['customer_id']}: unknown home warehouse")
        check(c["sales_rep_id"] in rep_ids, f"{c['customer_id']}: unknown sales rep")
        check(c["zip"] in zip_codes, f"{c['customer_id']}: ZIP {c['zip']} not in zips.json")
        check(c["trade_name"] in c["aliases"], f"{c['customer_id']}: trade name must be an alias")

    for row in inventory:
        check(row["sku"] in skus, f"inventory: unknown SKU {row['sku']}")
        check(row["warehouse_id"] in wh_ids, f"inventory: unknown warehouse {row['warehouse_id']}")
        check(row["on_hand"] - row["reserved"] == row["available"], f"inventory {row['warehouse_id']}/{row['sku']}: on_hand - reserved != available")
        check(row["available"] >= 0, f"inventory {row['warehouse_id']}/{row['sku']}: negative availability")
    check(len(inventory) == len(skus) * len(wh_ids), f"inventory: expected {len(skus) * len(wh_ids)} rows, found {len(inventory)}")

    prod_by_sku = {p["sku"]: p for p in products}
    for o in orders:
        check(o["customer_id"] in accounts, f"{o['order_id']}: unknown customer")
        check(o["warehouse_id"] in wh_ids, f"{o['order_id']}: unknown warehouse")
        check(o["sales_rep_id"] in rep_ids, f"{o['order_id']}: unknown rep")
        check(len(o["lines"]) >= 1, f"{o['order_id']}: no lines")
        check(sum(1 for l in o["lines"] if l["primary_item"]) == 1, f"{o['order_id']}: exactly one primary line expected")
        subtotal = 0.0
        for l in o["lines"]:
            check(l["sku"] in skus, f"{o['order_id']} line {l['line_no']}: unknown SKU {l['sku']}")
            if l["sku"] in prod_by_sku:
                expected = round(prod_by_sku[l["sku"]]["unit_price_usd"] * l["quantity"], 2)
                check(abs(expected - l["extended_price_usd"]) < 0.01, f"{o['order_id']} line {l['line_no']}: extended price {l['extended_price_usd']} != {expected}")
            subtotal += l["extended_price_usd"]
        check(abs(subtotal - o["subtotal_usd"]) < 0.01, f"{o['order_id']}: subtotal does not add up")

    for d in documents:
        check(d["content"] and len(d["content"]) > 80, f"{d['document_id']}: content is empty -- documents must carry full text, not links")
        check(d["status"] in ("active", "expired"), f"{d['document_id']}: bad status")
        for pid in d["passages"]:
            check(any(p["passage_id"] == pid for p in passages), f"{d['document_id']}: passage {pid} missing")
    for p in passages:
        check(p["document_id"] in doc_ids, f"{p['passage_id']}: unknown document {p['document_id']}")
    check(any(d["status"] == "expired" for d in documents), "documents: at least one expired document is needed for the expired-source demo")

    for a in approvals:
        check(a["product"] in families, f"product_approval: {a['product']} is not a product family")
    for w in warranty_rules:
        check(w.get("add_ons_required"), f"warranty_rules {w['tier']}: add_ons_required missing")

    for d in discounts:
        check(0 < d["percent"] < 50, f"{d['discount_id']}: percent out of range")
        if d.get("valid_from") and d.get("valid_to"):
            check(d["valid_from"] <= d["valid_to"], f"{d['discount_id']}: valid_from after valid_to")
        for fam in d["applies_to"].get("product_families", []):
            check(fam in families, f"{d['discount_id']}: unknown family {fam}")

    for c in contractors:
        check(c["zip"] in zip_codes, f"{c['contractor_id']}: ZIP {c['zip']} not in zips.json")
        check(4.0 <= c["rating"] <= 5.0, f"{c['contractor_id']}: rating out of range")
        check(c["certification_tier"] in ("presidents_club", "master_elite", "certified_plus", "certified"), f"{c['contractor_id']}: bad tier")
    covered = {c["zip"] for c in contractors}
    check(len(covered) >= 10, f"contractors: only {len(covered)} ZIPs covered; need at least 10")
    for z in zips:
        check(z["region_id"] in region_ids, f"zips {z['zip']}: unknown region {z['region_id']}")

    for r in reps:
        for acc in r["accounts"]:
            check(acc in accounts, f"{r['rep_id']}: unknown account {acc}")
    for e in emails:
        check(e["account_id"] in accounts, f"{e['email_id']}: unknown account")
        check(len(e["body"]) > 40, f"{e['email_id']}: body too short")

    names = set()
    for c in customers:
        names.add(c["customer_name"].lower())
        names.update(a.lower() for a in c["aliases"])
    for uc in use_cases.get("use_cases", []):
        prompt = uc["prompt"].lower()
        if uc["group"] == "Smart Order":
            check(any(n in prompt for n in names) or "tampa contractor" in prompt, f"{uc['id']}: prompt names no known customer")
        for m in re.findall(r"(?<![A-Z-])\b\d{5}\b", uc["prompt"]):
            check(m in zip_codes, f"{uc['id']}: ZIP {m} not in zips.json")
    for sc in use_cases.get("order_scenarios", []):
        check(sc["account_id"] in accounts, f"{sc['scenario_id']}: unknown account")
        check(sc["expected_sku"] in skus, f"{sc['scenario_id']}: unknown SKU")
    for sc in use_cases.get("advisor_scenarios", []):
        check(sc["region_id"] in region_ids, f"{sc['scenario_id']}: unknown region")
        for doc in str(sc["expected_source_doc"]).split(";"):
            check(doc in doc_ids, f"{sc['scenario_id']}: unknown source doc {doc}")

    if errors:
        print(f"{len(errors)} problem(s) found:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(
        f"ALL CHECKS PASSED: {len(products)} products, {len(customers)} customers, {len(inventory)} inventory rows, "
        f"{len(orders)} orders, {len(documents)} documents, {len(passages)} passages, {len(contractors)} contractors across "
        f"{len(covered)} ZIPs, {len(discounts)} discounts, {len(reps)} reps, {len(emails)} emails, {len(use_cases.get('use_cases', []))} use cases."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
