"""Build the Function App deploy zip.

Takes the original `Telecom-POC-deploy-with-GAF.zip` (repo root), keeps its
telecom section byte-for-byte, replaces the GAF-POC section with routes that
serve the full synthetic dataset through the shared gaf_catalog module, and
writes `Telecom-POC-deploy-with-GAF-v2.zip` next to it.

Zip contents:
  function_app.py      telecom routes (unchanged) + /api/gaf/* routes
  gaf_catalog.py       byte-identical copy of backend/app/services/gaf_catalog.py
  gaf_data/*.json      the data/ folder (documents carry full content)
  host.json, requirements.txt, .funcignore, openapi.json   as before (openapi extended)

Run:  python scripts/build_function_app_zip.py
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_ZIP = ROOT / "Telecom-POC-deploy-with-GAF.zip"
OUT_ZIP = ROOT / "Telecom-POC-deploy-with-GAF-v2.zip"
CATALOG = ROOT / "backend" / "app" / "services" / "gaf_catalog.py"
DATA = ROOT / "data"

GAF_MARKER = "# ============================================================================\n# GAF-POC"

GAF_SECTION = '''# ============================================================================
# GAF-POC -- Smart Order Helper + Product & Warranty Advisor + Contractors
# ============================================================================
# No auth (ANONYMOUS, matching the telecom section above -- same
# no-security-needed demo). Every route is a read-only lookup over the
# synthetic dataset in ./gaf_data, served through the shared GafCatalog
# (byte-identical to the backend's app/services/gaf_catalog.py, so the
# app's "local" mode and this "live" mode return the same envelopes).
# Knowledge documents return their FULL TEXT and passages -- the calling
# model cannot follow links, so nothing here is a URL to somewhere else.

from pathlib import Path

from gaf_catalog import CatalogError, GafCatalog

GAF = GafCatalog(Path(__file__).resolve().parent / "gaf_data")


def gaf_handler(operation: str, payload_factory: Callable[[], dict[str, Any]]) -> func.HttpResponse:
    """Same structured try/except shape as api_handler() above, without the
    subscriber resolution + personalize() step -- these routes are plain
    lookups, not "data for the currently authenticated caller"."""
    try:
        logger.info("gaf_api_request operation=%s", operation)
        return json_response(success_envelope(f"GAF-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}", payload_factory()))
    except CatalogError as exc:
        return json_response(
            {
                "statusCode": str(exc.status_code),
                "statusMessage": "Bad Request" if exc.status_code == 400 else "Not Found",
                "supportMessage": str(exc),
            },
            exc.status_code,
        )
    except Exception:
        error_id = f"ERR-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        logger.exception("gaf_api_error operation=%s error_id=%s", operation, error_id)
        return json_response(
            {
                "statusCode": "500",
                "statusMessage": "Internal Server Error",
                "supportMessage": "The request could not be processed.",
                "errorId": error_id,
            },
            500,
        )


def _p(req: func.HttpRequest, name: str) -> str | None:
    value = (req.params.get(name) or "").strip()
    return value or None


def _num(req: func.HttpRequest, name: str, default: float) -> float:
    try:
        return float(req.params.get(name) or default)
    except ValueError:
        return default


@app.route(route="gaf/products", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_products(req: func.HttpRequest) -> func.HttpResponse:
    """Product catalogue with unit prices, coverage, colour swatches, badges
    and recommended add-ons. ?sku=... for one product; ?family=... / ?type=...
    to filter; otherwise the active catalogue.  OpenAPI: gafGetProducts."""
    return gaf_handler("gafGetProducts", lambda: GAF.products(sku=_p(req, "sku"), family=_p(req, "family"), product_type=_p(req, "type")))


@app.route(route="gaf/inventory", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_inventory(req: func.HttpRequest) -> func.HttpResponse:
    """Per-warehouse stock (144 rows, 6 DCs). ?sku=... and/or ?warehouseId=...
    (at least one).  OpenAPI: gafGetInventory."""
    return gaf_handler("gafGetInventory", lambda: GAF.inventory(sku=_p(req, "sku"), warehouse_id=_p(req, "warehouseId")))


@app.route(route="gaf/customers", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_customers(req: func.HttpRequest) -> func.HttpResponse:
    """Customer accounts. ?accountId=..., ?name=... (name/trade name/alias,
    exact match wins over partial), ?zip=..., ?repId=...  OpenAPI: gafGetCustomers."""
    return gaf_handler("gafGetCustomers", lambda: GAF.customers(account_id=_p(req, "accountId"), name=_p(req, "name"), zip_code=_p(req, "zip"), rep_id=_p(req, "repId")))


@app.route(route="gaf/orders", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_orders(req: func.HttpRequest) -> func.HttpResponse:
    """Orders with priced lines. Filters: ?accountId, ?sku, ?orderId, ?repId,
    ?status.  OpenAPI: gafGetOrders."""
    return gaf_handler("gafGetOrders", lambda: GAF.orders(account_id=_p(req, "accountId"), sku=_p(req, "sku"), order_id=_p(req, "orderId"), rep_id=_p(req, "repId"), status=_p(req, "status")))


@app.route(route="gaf/documents", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_documents(req: func.HttpRequest) -> func.HttpResponse:
    """Approved knowledge documents WITH full content and citable passages.
    ?docId=... for one; ?content=false for metadata only. Each entry gets a
    computed status (active/expired) against today's date.  OpenAPI: gafGetDocuments."""
    include = (req.params.get("content") or "true").lower() != "false"
    return gaf_handler("gafGetDocuments", lambda: GAF.documents(doc_id=_p(req, "docId"), include_content=include))


@app.route(route="gaf/kb-passages", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_kb_passages(req: func.HttpRequest) -> func.HttpResponse:
    """Citable passages from active documents. ?docId, ?intent, ?q=<keywords>
    (keyword-scored).  OpenAPI: gafGetKbPassages."""
    return gaf_handler("gafGetKbPassages", lambda: GAF.kb_passages(doc_id=_p(req, "docId"), intent=_p(req, "intent"), query=_p(req, "q")))


@app.route(route="gaf/product-approval", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_product_approval(req: func.HttpRequest) -> func.HttpResponse:
    """Florida / Miami-Dade approval registry. ?product=... required.
    OpenAPI: gafGetProductApproval."""
    return gaf_handler("gafGetProductApproval", lambda: GAF.product_approval(_p(req, "product") or ""))


@app.route(route="gaf/warranty-rules", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_warranty_rules(req: func.HttpRequest) -> func.HttpResponse:
    """Warranty tier requirements. ?tier=... for one tier.  OpenAPI: gafGetWarrantyRules."""
    return gaf_handler("gafGetWarrantyRules", lambda: GAF.warranty_rules(tier=_p(req, "tier")))


@app.route(route="gaf/escalation-rules", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_escalation_rules(req: func.HttpRequest) -> func.HttpResponse:
    """The escalation-rules table, always in full.  OpenAPI: gafGetEscalationRules."""
    return gaf_handler("gafGetEscalationRules", GAF.escalation_rules)


@app.route(route="gaf/warehouses", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_warehouses(req: func.HttpRequest) -> func.HttpResponse:
    """Distribution centres. ?warehouseId=... for one.  OpenAPI: gafGetWarehouses."""
    return gaf_handler("gafGetWarehouses", lambda: GAF.warehouses(warehouse_id=_p(req, "warehouseId")))


@app.route(route="gaf/add-on-rules", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_add_on_rules(req: func.HttpRequest) -> func.HttpResponse:
    """Add-on recommendation rules with parsed quantity logic.  OpenAPI: gafGetAddOnRules."""
    return gaf_handler("gafGetAddOnRules", GAF.add_on_rules)


@app.route(route="gaf/discounts", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_discounts(req: func.HttpRequest) -> func.HttpResponse:
    """Automatic discounts (volume, seasonal, bundle, account) active on
    ?date=YYYY-MM-DD (default today).  OpenAPI: gafGetDiscounts."""
    return gaf_handler("gafGetDiscounts", lambda: GAF.discounts(on_date=_p(req, "date")))


@app.route(route="gaf/contractors", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_contractors(req: func.HttpRequest) -> func.HttpResponse:
    """GAF-certified contractors near ?zip=... or ?city=..., within ?radius
    miles (default 25), up to ?limit (default 10), optional ?minTier=
    certified|certified_plus|master_elite|presidents_club.  OpenAPI: gafGetContractors."""
    return gaf_handler("gafGetContractors", lambda: GAF.contractors(
        zip_code=_p(req, "zip"), city=_p(req, "city"), radius_miles=_num(req, "radius", 25.0),
        limit=int(_num(req, "limit", 10)), min_tier=_p(req, "minTier")))


@app.route(route="gaf/zips", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_zips(req: func.HttpRequest) -> func.HttpResponse:
    """ZIP -> city/county/region/HVHZ context. ?zip=... required.  OpenAPI: gafGetZip."""
    return gaf_handler("gafGetZip", lambda: GAF.zip_lookup(_p(req, "zip") or ""))


@app.route(route="gaf/counties", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_counties(req: func.HttpRequest) -> func.HttpResponse:
    """County regimes (HVHZ / non-HVHZ / non-Florida). ?regionId=... for one.
    OpenAPI: gafGetCounties."""
    return gaf_handler("gafGetCounties", lambda: GAF.counties(region_id=_p(req, "regionId")))


@app.route(route="gaf/sales-reps", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_sales_reps(req: func.HttpRequest) -> func.HttpResponse:
    """Sales reps with territories, commission rates and assigned accounts.
    ?repId=... for one.  OpenAPI: gafGetSalesReps."""
    return gaf_handler("gafGetSalesReps", lambda: GAF.sales_reps(rep_id=_p(req, "repId")))


@app.route(route="gaf/emails", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_emails(req: func.HttpRequest) -> func.HttpResponse:
    """Synthetic customer inbox for the email agent. ?emailId, ?accountId, ?repId.
    OpenAPI: gafGetEmails."""
    return gaf_handler("gafGetEmails", lambda: GAF.emails(email_id=_p(req, "emailId"), account_id=_p(req, "accountId"), rep_id=_p(req, "repId")))


@app.route(route="gaf/use-cases", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def gaf_use_cases(req: func.HttpRequest) -> func.HttpResponse:
    """Demo use cases plus the workbook's order/advisor scenarios.  OpenAPI: gafGetUseCases."""
    return gaf_handler("gafGetUseCases", GAF.use_cases)
'''

NEW_PATHS = {
    "/api/gaf/kb-passages": ("gafGetKbPassages", "Citable passages from active knowledge documents", ["docId", "intent", "q"]),
    "/api/gaf/warehouses": ("gafGetWarehouses", "Distribution centres", ["warehouseId"]),
    "/api/gaf/add-on-rules": ("gafGetAddOnRules", "Add-on recommendation rules", []),
    "/api/gaf/discounts": ("gafGetDiscounts", "Automatic discounts active on a date", ["date"]),
    "/api/gaf/contractors": ("gafGetContractors", "GAF-certified contractors near a ZIP or city", ["zip", "city", "radius", "limit", "minTier"]),
    "/api/gaf/zips": ("gafGetZip", "ZIP to county/region context", ["zip"]),
    "/api/gaf/counties": ("gafGetCounties", "County regimes", ["regionId"]),
    "/api/gaf/sales-reps": ("gafGetSalesReps", "Sales reps, territories, commission, accounts", ["repId"]),
    "/api/gaf/emails": ("gafGetEmails", "Synthetic customer inbox", ["emailId", "accountId", "repId"]),
    "/api/gaf/use-cases": ("gafGetUseCases", "Demo use cases and workbook scenarios", []),
}
EXTRA_PARAMS = {
    "/api/gaf/products": ["family", "type"],
    "/api/gaf/inventory": ["warehouseId"],
    "/api/gaf/customers": ["zip", "repId"],
    "/api/gaf/orders": ["orderId", "repId", "status"],
    "/api/gaf/documents": ["content"],
}


def _extend_openapi(raw: str) -> str:
    spec = json.loads(raw)
    spec["info"]["version"] = "2.0.0"
    spec["info"]["description"] += (
        " v2: GAF routes serve the full synthetic dataset (24 products with prices, 18 accounts, 144 inventory rows, "
        "45 priced orders, knowledge documents with full text, add-on rules, discounts, contractors, sales reps, inbox, use cases)."
    )
    generic = {"$ref": "#/components/schemas/ErrorResponse"}
    for path, (op_id, summary, params) in NEW_PATHS.items():
        spec["paths"][path] = {"get": {
            "operationId": op_id, "summary": summary, "tags": ["GAF-POC"],
            "parameters": [{"name": p, "in": "query", "required": False, "schema": {"type": "string"}} for p in params],
            "responses": {
                "200": {"description": "Success envelope; see gaf_catalog.py for the data shape.",
                        "content": {"application/json": {"schema": {"type": "object"}}}},
                "400": {"description": "Bad request", "content": {"application/json": {"schema": generic}}},
                "404": {"description": "Not found", "content": {"application/json": {"schema": generic}}},
            },
        }}
    for path, params in EXTRA_PARAMS.items():
        get = spec["paths"].get(path, {}).get("get")
        if not get:
            continue
        existing = {p["name"] for p in get.get("parameters", [])}
        for p in params:
            if p not in existing:
                get.setdefault("parameters", []).append({"name": p, "in": "query", "required": False, "schema": {"type": "string"}})
    return json.dumps(spec, indent=2, ensure_ascii=False)


def main() -> None:
    with zipfile.ZipFile(SRC_ZIP) as src:
        original = src.read("function_app.py").decode("utf-8")
        others = {n: src.read(n) for n in src.namelist() if n != "function_app.py"}

    idx = original.index(GAF_MARKER)
    telecom_part = original[:idx]
    # The original module docstring describes the old 8-route GAF section;
    # everything below the marker is regenerated, the telecom code is untouched.
    new_source = telecom_part + GAF_SECTION
    assert "def profile(" in telecom_part and "def offers(" in telecom_part

    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr("function_app.py", new_source)
        out.writestr("gaf_catalog.py", CATALOG.read_text(encoding="utf-8"))
        for name, blob in others.items():
            if name == "openapi.json":
                out.writestr(name, _extend_openapi(blob.decode("utf-8")))
            else:
                out.writestr(name, blob)
        for path in sorted(DATA.rglob("*.json")):
            rel = path.relative_to(DATA).as_posix()
            if rel.startswith(("metrics/", "orders/", "review_queue")):
                continue
            out.write(path, f"gaf_data/{rel}")
    print(f"wrote {OUT_ZIP}")
    with zipfile.ZipFile(OUT_ZIP) as z:
        for n in z.namelist():
            print("  ", n)


if __name__ == "__main__":
    main()
