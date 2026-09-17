"""Local transport for gaf_api_client: serves the synthetic dataset under
data/ through the shared GafCatalog, in the exact envelope shape the live
Function App returns (both hosts run the same gaf_catalog.py). Orchestrators
never see which transport answered.

ALL DATA SERVED BY THIS MODULE IS SYNTHETIC DEMO DATA.
"""

from typing import Any, Callable, Optional

from app.config import DATA_DIR
from app.services.gaf_api_client import ToolResult
from app.services.gaf_catalog import CatalogError, GafCatalog

catalog = GafCatalog(DATA_DIR)


def _wrap(fn: Callable[[], dict[str, Any]]) -> ToolResult:
    try:
        return ToolResult(success=True, data={"data": fn()}, status_code=200)
    except CatalogError as exc:
        return ToolResult(success=False, error="gaf_api_not_found" if exc.status_code == 404 else "gaf_api_bad_request",
                          status_code=exc.status_code, data={"supportMessage": str(exc)})


# Raw snake_case loaders for callers that search dataset text directly.
def load_customers() -> list[dict[str, Any]]:
    return catalog.raw("customers.json")


def load_products() -> list[dict[str, Any]]:
    return catalog.raw("products.json")


def load_inventory() -> list[dict[str, Any]]:
    return catalog.raw("inventory.json")


def load_product_approval() -> list[dict[str, Any]]:
    return catalog.raw("product_approval.json")


async def get_customers(account_id: Optional[str] = None, name: Optional[str] = None,
                        zip_code: Optional[str] = None, rep_id: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.customers(account_id=account_id, name=name, zip_code=zip_code, rep_id=rep_id))


async def get_products(sku: Optional[str] = None, family: Optional[str] = None,
                       product_type: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.products(sku=sku, family=family, product_type=product_type))


async def get_inventory(sku: Optional[str] = None, warehouse_id: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.inventory(sku=sku, warehouse_id=warehouse_id))


async def get_orders(account_id: Optional[str] = None, sku: Optional[str] = None, order_id: Optional[str] = None,
                     rep_id: Optional[str] = None, status: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.orders(account_id=account_id, sku=sku, order_id=order_id, rep_id=rep_id, status=status))


async def get_documents(doc_id: Optional[str] = None, include_content: bool = True) -> ToolResult:
    return _wrap(lambda: catalog.documents(doc_id=doc_id, include_content=include_content))


async def get_kb_passages(doc_id: Optional[str] = None, intent: Optional[str] = None, query: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.kb_passages(doc_id=doc_id, intent=intent, query=query))


async def get_product_approval(product: str) -> ToolResult:
    return _wrap(lambda: catalog.product_approval(product))


async def get_warranty_rules(tier: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.warranty_rules(tier=tier))


async def get_escalation_rules() -> ToolResult:
    return _wrap(catalog.escalation_rules)


async def get_warehouses(warehouse_id: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.warehouses(warehouse_id=warehouse_id))


async def get_add_on_rules() -> ToolResult:
    return _wrap(catalog.add_on_rules)


async def get_discounts(on_date: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.discounts(on_date=on_date))


async def get_contractors(zip_code: Optional[str] = None, city: Optional[str] = None, radius_miles: float = 25.0,
                          limit: int = 10, min_tier: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.contractors(zip_code=zip_code, city=city, radius_miles=radius_miles, limit=limit, min_tier=min_tier))


async def get_zip(zip_code: str) -> ToolResult:
    return _wrap(lambda: catalog.zip_lookup(zip_code))


async def get_counties(region_id: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.counties(region_id=region_id))


async def get_sales_reps(rep_id: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.sales_reps(rep_id=rep_id))


async def get_emails(email_id: Optional[str] = None, account_id: Optional[str] = None, rep_id: Optional[str] = None) -> ToolResult:
    return _wrap(lambda: catalog.emails(email_id=email_id, account_id=account_id, rep_id=rep_id))


async def get_use_cases() -> ToolResult:
    return _wrap(catalog.use_cases)
