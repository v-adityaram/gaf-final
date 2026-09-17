"""Shared GAF-POC data catalogue.

One module, two hosts: the FastAPI backend reads it through
app/services/local_data_repository.py (GAF_DATA_SOURCE=local), and the Azure
Function App ships a byte-identical copy next to function_app.py and serves
the same envelopes over /api/gaf/*. Because both transports build their
responses here, "local" and "live" cannot drift apart.

Stdlib only -- no app.* imports, no pydantic -- so the file can be dropped
into the Function App zip unchanged (see scripts/build_function_app_zip.py).

Every public method returns the camelCase JSON envelope the orchestrators
read, or raises CatalogError(status_code) for a bad/unknown lookup.

ALL DATA SERVED BY THIS MODULE IS SYNTHETIC DEMO DATA.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Optional


class CatalogError(ValueError):
    def __init__(self, message: str, status_code: int = 404):
        super().__init__(message)
        self.status_code = status_code


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class GafCatalog:
    def __init__(self, data_dir: str | os.PathLike[str]):
        self.data_dir = Path(data_dir)
        self._cache: dict[str, tuple[float, Any]] = {}

    # ------------------------------------------------------------- loading

    def _load(self, name: str) -> Any:
        path = self.data_dir / name
        mtime = path.stat().st_mtime
        cached = self._cache.get(name)
        if cached and cached[0] == mtime:
            return cached[1]
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._cache[name] = (mtime, data)
        return data

    # Raw (snake_case) accessors for callers that search the dataset's own
    # text rather than the envelope shape.
    def raw(self, name: str) -> Any:
        return self._load(name)

    # ------------------------------------------------------------ products

    @staticmethod
    def _product_envelope(p: dict[str, Any]) -> dict[str, Any]:
        env: dict[str, Any] = {
            "sku": p["sku"],
            "productName": p["product_name"],
            "productFamily": p["product_family"],
            "colour": p.get("color"),
            "colourCollection": p.get("color_collection"),
            "soldIn": p["unit"],
            "bundlesPerSquare": p["bundles_per_square"],
            "productType": p["category"],
            "active": p.get("active", True),
            "unitPriceUsd": p["unit_price_usd"],
            "priceUnit": p["unit"],
            "pricePerSquareUsd": round(p["unit_price_usd"] * p["bundles_per_square"], 2) if p["bundles_per_square"] else None,
            "coverageSqftPerUnit": p["coverage_sqft_per_unit"],
            "qualifyingAddOn": p["qualifying_add_on"],
            "websiteCategory": p["website_category"],
            "swatchHex": p.get("swatch_hex"),
            "imageUrl": p.get("image_url"),
            "badges": p.get("badges", []),
            "priceTier": p.get("price_tier"),
            "recommendedAddOns": p.get("recommended_add_ons", []),
            "ridgeCapMatch": p.get("ridge_cap_match"),
        }
        if p.get("add_on_reason"):
            env["addOnReason"] = p["add_on_reason"]
        loc = p.get("large_order_delivery_check")
        if loc:
            env["largeOrderDeliveryCheck"] = {"thresholdSquares": loc["threshold_squares"], "action": loc["action"]}
        sac = p.get("site_access_check")
        if sac:
            env["siteAccessCheck"] = {"thresholdSquares": sac["threshold_squares"], "action": sac["action"]}
        return env

    def products(self, sku: Optional[str] = None, family: Optional[str] = None,
                 product_type: Optional[str] = None, include_inactive: bool = False) -> dict[str, Any]:
        rows = self._load("products.json")
        if sku:
            needle = sku.strip().upper()
            rows = [r for r in rows if r["sku"].upper() == needle]
            if not rows:
                raise CatalogError(f"Unknown sku '{needle}'.", 404)
        else:
            if not include_inactive:
                rows = [r for r in rows if r.get("active", True)]
            if family:
                f = family.strip().lower()
                rows = [r for r in rows if r["product_family"].lower() == f]
            if product_type:
                t = product_type.strip().lower()
                rows = [r for r in rows if r["category"].lower() == t]
        return {"products": [self._product_envelope(r) for r in rows]}

    def product(self, sku: str) -> Optional[dict[str, Any]]:
        needle = sku.strip().upper()
        for r in self._load("products.json"):
            if r["sku"].upper() == needle:
                return self._product_envelope(r)
        return None

    # ----------------------------------------------------------- inventory

    @staticmethod
    def _inventory_envelope(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "sku": r["sku"],
            "warehouse": r["warehouse"],
            "warehouseId": r["warehouse_id"],
            "quantityAvailable": r["available"],
            "unit": r["unit"],
            "restockDate": r.get("expected_receipt_date"),
            "stockStatus": r.get("stock_status"),
            "reservedQuantity": r.get("reserved"),
            "onHandQuantity": r.get("on_hand"),
            "safetyStock": r.get("safety_stock"),
            "inboundQuantity": r.get("inbound_qty"),
            "supplierLeadDays": r.get("supplier_lead_days"),
            "backorderRisk": r.get("backorder_risk"),
            "inventoryConfidence": r.get("inventory_confidence"),
            "asOfDate": r.get("as_of_date"),
        }

    def inventory(self, sku: Optional[str] = None, warehouse_id: Optional[str] = None) -> dict[str, Any]:
        if not sku and not warehouse_id:
            raise CatalogError("The sku (or warehouseId) query parameter is required.", 400)
        rows = self._load("inventory.json")
        if sku:
            needle = sku.strip().upper()
            rows = [r for r in rows if r["sku"].upper() == needle]
        if warehouse_id:
            w = warehouse_id.strip().upper()
            rows = [r for r in rows if r["warehouse_id"].upper() == w]
        return {"inventory": [self._inventory_envelope(r) for r in rows]}

    # ----------------------------------------------------------- customers

    @staticmethod
    def _customer_envelope(c: dict[str, Any]) -> dict[str, Any]:
        return {
            "accountId": c["customer_id"],
            "customerName": c["customer_name"],
            "tradeName": c.get("trade_name"),
            "aliases": c.get("aliases", []),
            "customerType": c.get("customer_type"),
            "contactName": c.get("contact_name"),
            "email": c.get("email"),
            "phone": c.get("phone"),
            "city": c.get("city"),
            "state": c.get("state"),
            "address": c.get("address"),
            "zip": c.get("zip"),
            "defaultShipToCity": c["default_ship_to_city"],
            "creditLimit": c["credit_limit"],
            "currentBalance": c["current_balance"],
            "availableCredit": c["available_credit"],
            "creditLimitUsedPercent": c["credit_utilization_percent"],
            "creditStatus": c["credit_status"],
            "creditHold": c["credit_hold"],
            "paymentTerms": c.get("payment_terms"),
            "preferredChannel": c.get("preferred_channel"),
            "poPrefix": c.get("po_prefix"),
            "homeWarehouseId": c.get("home_warehouse_id"),
            "salesRepId": c.get("sales_rep_id"),
            "accountStatus": c.get("account_status"),
        }

    def customers(self, account_id: Optional[str] = None, name: Optional[str] = None,
                  zip_code: Optional[str] = None, rep_id: Optional[str] = None) -> dict[str, Any]:
        rows = self._load("customers.json")
        if account_id:
            needle = account_id.strip().upper()
            rows = [r for r in rows if r["customer_id"].upper() == needle]
            if not rows:
                raise CatalogError(f"Unknown accountId '{needle}'.", 404)
        elif name:
            needle = re.sub(r"\s+", " ", name.strip().lower())

            def names(r: dict[str, Any]) -> list[str]:
                return [r["customer_name"], r.get("trade_name") or ""] + list(r.get("aliases", []))

            exact = [r for r in rows if any(n.strip().lower() == needle for n in names(r) if n)]
            # Exact full-name/alias matches win outright; only a genuinely
            # partial query surfaces the "two accounts match" ambiguity.
            rows = exact or [r for r in rows if any(needle in n.lower() for n in names(r) if n)]
            if not rows:
                raise CatalogError(f"No customer name or alias matches '{name}'.", 404)
        if zip_code:
            z = zip_code.strip()
            rows = [r for r in rows if r.get("zip") == z]
        if rep_id:
            rp = rep_id.strip().upper()
            rows = [r for r in rows if (r.get("sales_rep_id") or "").upper() == rp]
        return {"customers": [self._customer_envelope(r) for r in rows]}

    # -------------------------------------------------------------- orders

    @staticmethod
    def _order_envelope(o: dict[str, Any]) -> dict[str, Any]:
        return {
            "orderId": o["order_id"],
            "accountId": o["customer_id"],
            "customerPo": o.get("customer_po"),
            "sku": o.get("sku"),
            "quantity": o.get("quantity"),
            "unit": o.get("unit"),
            "squares": o.get("squares"),
            "orderDate": o["order_date"],
            "deliveryDate": o.get("delivery_date"),
            "deliveryCity": o.get("delivery_city"),
            "shipToAddress": o.get("ship_to_address"),
            "warehouseId": o.get("warehouse_id"),
            "channel": o.get("channel"),
            "status": o.get("status"),
            "deliveryMethod": o.get("delivery_method"),
            "captureConfidence": o.get("capture_confidence"),
            "humanConfirmed": o.get("human_confirmed"),
            "duplicatePoCount": o.get("duplicate_po_count"),
            "salesRepId": o.get("sales_rep_id"),
            "lines": [{
                "lineNo": l["line_no"], "sku": l["sku"], "productName": l.get("product_name"),
                "quantity": l["quantity"], "unit": l["unit"], "unitPriceUsd": l.get("unit_price_usd"),
                "extendedPriceUsd": l.get("extended_price_usd"), "colour": l.get("color"),
                "productType": l.get("product_type"), "primaryItem": l.get("primary_item", False),
            } for l in o.get("lines", [])],
            "subtotalUsd": o.get("subtotal_usd"),
            "totalUsd": o.get("total_usd"),
        }

    def orders(self, account_id: Optional[str] = None, sku: Optional[str] = None, order_id: Optional[str] = None,
               rep_id: Optional[str] = None, status: Optional[str] = None) -> dict[str, Any]:
        rows = self._load("orders.json")
        if order_id:
            oid = order_id.strip().upper()
            rows = [r for r in rows if r["order_id"].upper() == oid]
        if account_id:
            acc = account_id.strip().upper()
            rows = [r for r in rows if r["customer_id"].upper() == acc]
        if sku:
            s = sku.strip().upper()
            rows = [r for r in rows if (r.get("sku") or "").upper() == s or any(l["sku"].upper() == s for l in r.get("lines", []))]
        if rep_id:
            rp = rep_id.strip().upper()
            rows = [r for r in rows if (r.get("sales_rep_id") or "").upper() == rp]
        if status:
            st = status.strip().lower()
            rows = [r for r in rows if (r.get("status") or "").lower() == st]
        rows = sorted(rows, key=lambda r: r["order_date"], reverse=True)
        return {"orders": [self._order_envelope(r) for r in rows]}

    # ----------------------------------------------------------- documents

    def _passage_envelope(self, p: dict[str, Any]) -> dict[str, Any]:
        return {
            "passageId": p["passage_id"], "docId": p["document_id"], "intentTag": p["intent_tag"],
            "text": p["text"], "regionScope": p.get("region_scope"), "allowedAction": p.get("allowed_action"),
            "provenance": p.get("provenance"),
        }

    def _document_envelope(self, d: dict[str, Any], include_content: bool) -> dict[str, Any]:
        today = date.today().isoformat()
        valid_until = d.get("expiration_date")
        expired = d.get("status") == "expired" or (valid_until is not None and valid_until < today)
        env: dict[str, Any] = {
            "docId": d["document_id"],
            "title": d["title"],
            "topic": d["topic"],
            "version": d["version"],
            "effectiveDate": d.get("effective_date"),
            "validUntil": valid_until,
            "status": "expired" if expired else "active",
            "source": d.get("source"),
            "usageNote": d.get("usage_note"),
        }
        if include_content:
            passages = [p for p in self._load("kb_passages.json") if p["document_id"] == d["document_id"]]
            env["passages"] = [self._passage_envelope(p) for p in passages]
            env["content"] = d.get("content")
        return env

    def documents(self, doc_id: Optional[str] = None, include_content: bool = True) -> dict[str, Any]:
        rows = self._load("documents.json")
        if doc_id:
            needle = doc_id.strip().upper()
            rows = [r for r in rows if r["document_id"].upper() == needle]
            if not rows:
                raise CatalogError(f"Unknown docId '{needle}'.", 404)
        return {"documents": [self._document_envelope(r, include_content) for r in rows]}

    def kb_passages(self, doc_id: Optional[str] = None, intent: Optional[str] = None,
                    query: Optional[str] = None, active_only: bool = True) -> dict[str, Any]:
        rows = self._load("kb_passages.json")
        if active_only:
            active_docs = {d["docId"] for d in self.documents(include_content=False)["documents"] if d["status"] == "active"}
            rows = [r for r in rows if r["document_id"] in active_docs]
        if doc_id:
            needle = doc_id.strip().upper()
            rows = [r for r in rows if r["document_id"].upper() == needle]
        if intent:
            i = intent.strip().upper()
            rows = [r for r in rows if r["intent_tag"].upper() == i]
        if query:
            terms = {t for t in re.findall(r"[a-z0-9]{3,}", query.lower())}
            scored = []
            for r in rows:
                words = set(re.findall(r"[a-z0-9]{3,}", r["text"].lower()))
                hits = len(terms & words)
                if hits:
                    scored.append((hits, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            rows = [r for _, r in scored]
            return {"passages": [dict(self._passage_envelope(r), matchScore=h) for h, r in scored]}
        return {"passages": [self._passage_envelope(r) for r in rows]}

    # ---------------------------------------------------- product approval

    def product_approval(self, product: str) -> dict[str, Any]:
        rows = self._load("product_approval.json")
        needle = (product or "").strip().lower()
        if not needle:
            raise CatalogError("The product query parameter is required.", 400)
        exact = {r["product"] for r in rows if r["product"].lower() == needle}
        if exact:
            names = exact
        else:
            # Only resolve a partial match if it names exactly one product
            # family -- never merge approval numbers from two products.
            partial = {r["product"] for r in rows if needle in r["product"].lower() or r["product"].lower() in needle}
            names = partial if len(partial) == 1 else set()
        if not names:
            raise CatalogError(f"No approval record for product '{product}'.", 404)
        name = next(iter(names))
        result: dict[str, Any] = {"product": name}
        for r in rows:
            if r["product"] == name and r.get("contract_field"):
                result[r["contract_field"]] = r["approval_number"]
        return result

    # ------------------------------------------------------ warranty rules

    def warranty_rules(self, tier: Optional[str] = None) -> dict[str, Any]:
        rows = self._load("warranty_rules.json")
        if tier:
            t = tier.strip().lower()
            rows = [r for r in rows if r["tier"].lower() == t]
            if not rows:
                raise CatalogError(f"Unknown tier '{tier}'.", 404)
        return {"tiers": [{
            "tier": r["tier"], "installMethod": r["install_method"],
            "addOnsRequired": r.get("add_ons_required", []),
            "windCoverage": r["wind_coverage"],
        } for r in rows]}

    def escalation_rules(self) -> dict[str, Any]:
        return {"rules": [{"topic": r["topic"], "action": r["action"], "sendTo": r.get("send_to")}
                          for r in self._load("escalation_rules.json")]}

    # ---------------------------------------------------------- warehouses

    def warehouses(self, warehouse_id: Optional[str] = None) -> dict[str, Any]:
        rows = self._load("warehouses.json")
        if warehouse_id:
            w = warehouse_id.strip().upper()
            rows = [r for r in rows if r["warehouse_id"].upper() == w]
            if not rows:
                raise CatalogError(f"Unknown warehouseId '{warehouse_id}'.", 404)
        return {"warehouses": [{
            "warehouseId": r["warehouse_id"], "name": r["name"], "city": r["city"], "state": r["state"],
            "latitude": r["latitude"], "longitude": r["longitude"],
            "dailyOrderCapacity": r["daily_order_capacity"], "storageCapacityPallets": r["storage_capacity_pallets"],
        } for r in rows]}

    # -------------------------------------------------------- add-on rules

    def add_on_rules(self) -> dict[str, Any]:
        return {"rules": [{
            "ruleId": r["rule_id"], "trigger": r["trigger"], "recommendationType": r["recommendation_type"],
            "suggestedSku": r.get("suggested_sku"), "rationale": r["rationale"], "quantityLogic": r["quantity_logic"],
            "ruleGroup": r["rule_group"], "priority": r["priority"], "qtyPer": r.get("qty_per"),
            "qtyUnit": r.get("qty_unit"), "perSquares": r.get("per_squares"), "perRidgeFeet": r.get("per_ridge_feet"),
        } for r in self._load("add_on_rules.json")]}

    # ----------------------------------------------------------- discounts

    def discounts(self, on_date: Optional[str] = None, active_only: bool = True) -> dict[str, Any]:
        rows = self._load("discounts.json")
        today = (on_date or date.today().isoformat())[:10]
        out = []
        for r in rows:
            active = (r.get("valid_from") is None or r["valid_from"] <= today) and (r.get("valid_to") is None or today <= r["valid_to"])
            if active_only and not active:
                continue
            out.append({
                "discountId": r["discount_id"], "name": r["name"], "kind": r["kind"], "percent": r["percent"],
                "appliesTo": {
                    "productTypes": r["applies_to"].get("product_types", []),
                    "productFamilies": r["applies_to"].get("product_families", []),
                    "customerTypes": r["applies_to"].get("customer_types", []),
                    "skus": r["applies_to"].get("skus", []),
                },
                "minSquares": r.get("min_squares"), "validFrom": r.get("valid_from"), "validTo": r.get("valid_to"),
                "stackable": r.get("stackable", True), "autoApply": r.get("auto_apply", True),
                "requiresCategories": r.get("requires_categories", []), "badge": r.get("badge"),
                "description": r.get("description"), "active": active,
            })
        return {"discounts": out, "asOf": today}

    # --------------------------------------------------------- contractors

    def zip_lookup(self, zip_code: str) -> dict[str, Any]:
        z = (zip_code or "").strip()
        for r in self._load("zips.json"):
            if r["zip"] == z:
                return {"zip": r["zip"], "city": r["city"], "state": r["state"], "county": r["county"],
                        "regionId": r["region_id"], "latitude": r["latitude"], "longitude": r["longitude"]}
        raise CatalogError(f"ZIP '{z}' is not in the prototype directory.", 404)

    def _city_lookup(self, city: str) -> dict[str, Any]:
        c = (city or "").strip().lower()
        for r in self._load("zips.json"):
            if r["city"].lower() == c:
                return self.zip_lookup(r["zip"])
        raise CatalogError(f"City '{city}' is not in the prototype directory.", 404)

    def contractors(self, zip_code: Optional[str] = None, city: Optional[str] = None,
                    radius_miles: float = 25.0, limit: int = 10,
                    min_tier: Optional[str] = None) -> dict[str, Any]:
        if zip_code:
            loc = self.zip_lookup(zip_code)
        elif city:
            loc = self._city_lookup(city)
        else:
            raise CatalogError("Provide a zip or city.", 400)
        rank = {"certified": 1, "certified_plus": 2, "master_elite": 3, "presidents_club": 4}
        floor = rank.get((min_tier or "").strip().lower(), 0)
        rows = []
        for r in self._load("contractors.json"):
            if rank.get(r["certification_tier"], 0) < floor:
                continue
            dist = _haversine_miles(loc["latitude"], loc["longitude"], r["latitude"], r["longitude"])
            rows.append((dist, r))
        within = [(d, r) for d, r in rows if d <= radius_miles]
        expanded = False
        if not within:
            within = sorted(rows, key=lambda x: x[0])[:limit]
            expanded = True
        within.sort(key=lambda x: (x[0]))
        out = []
        for dist, r in within[:limit]:
            out.append({
                "contractorId": r["contractor_id"], "name": r["name"], "city": r["city"], "state": r["state"], "zip": r["zip"],
                "distanceMiles": round(dist, 1), "phone": r["phone"], "rating": r["rating"], "reviewCount": r["review_count"],
                "certificationTier": r["certification_tier"], "certificationLabel": r["certification_label"],
                "warrantiesOffered": r["warranties_offered"], "awards": r["awards"], "specialties": r["specialties"],
                "yearsCertified": r["years_certified"], "residential": r["residential"], "commercial": r["commercial"],
                "acceptsQuoteRequests": r["accepts_quote_requests"],
            })
        return {"location": loc, "radiusMiles": radius_miles, "radiusExpanded": expanded, "contractors": out}

    def counties(self, region_id: Optional[str] = None) -> dict[str, Any]:
        rows = self._load("counties.json")
        if region_id:
            rid = region_id.strip().upper()
            rows = [r for r in rows if r["region_id"].upper() == rid]
        return {"counties": [{
            "regionId": r["region_id"], "county": r["county"], "state": r["state"], "regime": r["regime"],
            "approvalContext": r["approval_context"], "assistantBehavior": r["assistant_behavior"],
        } for r in rows]}

    # ---------------------------------------------------------- sales reps

    def sales_reps(self, rep_id: Optional[str] = None) -> dict[str, Any]:
        rows = self._load("sales_reps.json")
        if rep_id:
            rp = rep_id.strip().upper()
            rows = [r for r in rows if r["rep_id"].upper() == rp]
            if not rows:
                raise CatalogError(f"Unknown repId '{rep_id}'.", 404)
        return {"salesReps": [{
            "repId": r["rep_id"], "name": r["name"], "initials": r["initials"], "title": r["title"], "email": r["email"],
            "phone": r["phone"], "territory": r["territory"], "states": r["states"], "cities": r["cities"],
            "commissionRate": r["commission_rate"], "quotaUsd": r["quota_usd"], "accounts": r["accounts"],
        } for r in rows]}

    # -------------------------------------------------------------- emails

    def emails(self, email_id: Optional[str] = None, account_id: Optional[str] = None,
               rep_id: Optional[str] = None) -> dict[str, Any]:
        rows = self._load("emails.json")
        if email_id:
            e = email_id.strip().upper()
            rows = [r for r in rows if r["email_id"].upper() == e]
            if not rows:
                raise CatalogError(f"Unknown emailId '{email_id}'.", 404)
        if account_id:
            a = account_id.strip().upper()
            rows = [r for r in rows if r["account_id"].upper() == a]
        if rep_id:
            accounts = {c["customer_id"] for c in self._load("customers.json") if (c.get("sales_rep_id") or "").upper() == rep_id.strip().upper()}
            rows = [r for r in rows if r["account_id"] in accounts]
        return {"emails": [{
            "emailId": r["email_id"], "fromName": r["from_name"], "fromEmail": r["from_email"], "accountId": r["account_id"],
            "customerName": r["customer_name"], "tradeName": r.get("trade_name"), "subject": r["subject"],
            "receivedAt": r["received_at"], "category": r.get("category"), "body": r["body"], "read": r.get("read", False),
        } for r in rows]}

    # ----------------------------------------------------------- use cases

    def use_cases(self) -> dict[str, Any]:
        d = self._load("demo_scenarios/use_cases.json")
        return {"useCases": d["use_cases"], "orderScenarios": d["order_scenarios"], "advisorScenarios": d["advisor_scenarios"]}
