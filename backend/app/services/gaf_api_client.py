"""Thin client for the GAF-POC routes (/api/gaf/*) on the Telecom-POC +
GAF-POC Function App. Same ToolResult pattern telecom-assistant's own
telecom_client.py uses: every call returns a structured result, never
raises, and a failure degrades the orchestrator to "needs clarification" /
"no approved source" rather than crashing or inventing data.

Each function below has two transports, chosen by config.GAF_DATA_SOURCE:
"local" (default) reads the synthetic dataset under data/ via
local_data_repository -- no network -- and "live" does the HTTP call to the
Function App. Both transports build responses with the same gaf_catalog
module, so the envelopes are identical either way.
"""

import logging

import httpx
from pydantic import BaseModel

from app.config import GAF_API_BASE_URL, GAF_DATA_SOURCE

logger = logging.getLogger("gaf_demo.gaf_api_client")

TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)

# Read at call time (not just import time) so tests can monkeypatch this
# module's own DATA_SOURCE attribute to force one transport regardless of
# the process's .env.
DATA_SOURCE = GAF_DATA_SOURCE


class ToolResult(BaseModel):
    success: bool
    data: dict | None = None
    error: str | None = None
    status_code: int | None = None


def _local():
    # Deferred import: local_data_repository imports ToolResult from this
    # module, so importing it at module load time would be circular.
    from app.services import local_data_repository

    return local_data_repository


async def _get(path: str, params: dict[str, object]) -> ToolResult:
    url = f"{GAF_API_BASE_URL}{path}"
    clean_params = {k: str(v) for k, v in params.items() if v not in (None, "", False)}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(url, params=clean_params)
        response.raise_for_status()
        return ToolResult(success=True, data=response.json(), status_code=response.status_code)

    except httpx.TimeoutException:
        logger.warning("gaf_api_timeout path=%s", path)
        return ToolResult(success=False, error="gaf_api_timeout")

    except httpx.HTTPStatusError as exc:
        # 404 here is a normal "no match" (unknown sku/accountId/etc.), not a
        # real error -- the response body still carries a real envelope.
        try:
            body = exc.response.json()
        except ValueError:
            body = None
        error = "gaf_api_not_found" if exc.response.status_code == 404 else "gaf_api_bad_request"
        return ToolResult(success=False, error=error, status_code=exc.response.status_code, data=body)

    except httpx.RequestError:
        logger.warning("gaf_api_request_error path=%s", path)
        return ToolResult(success=False, error="gaf_api_unreachable")

    except ValueError:
        logger.warning("gaf_api_invalid_response path=%s", path)
        return ToolResult(success=False, error="gaf_api_invalid_response")


async def get_products(sku: str | None = None, family: str | None = None, product_type: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_products(sku=sku, family=family, product_type=product_type)
    return await _get("/api/gaf/products", {"sku": sku, "family": family, "type": product_type})


async def get_inventory(sku: str | None = None, warehouse_id: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_inventory(sku=sku, warehouse_id=warehouse_id)
    return await _get("/api/gaf/inventory", {"sku": sku, "warehouseId": warehouse_id})


async def get_customers(account_id: str | None = None, name: str | None = None,
                        zip_code: str | None = None, rep_id: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_customers(account_id=account_id, name=name, zip_code=zip_code, rep_id=rep_id)
    return await _get("/api/gaf/customers", {"accountId": account_id, "name": name, "zip": zip_code, "repId": rep_id})


async def get_orders(account_id: str | None = None, sku: str | None = None, order_id: str | None = None,
                     rep_id: str | None = None, status: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_orders(account_id=account_id, sku=sku, order_id=order_id, rep_id=rep_id, status=status)
    return await _get("/api/gaf/orders", {"accountId": account_id, "sku": sku, "orderId": order_id, "repId": rep_id, "status": status})


async def get_documents(doc_id: str | None = None, include_content: bool = True) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_documents(doc_id=doc_id, include_content=include_content)
    return await _get("/api/gaf/documents", {"docId": doc_id, "content": "true" if include_content else "false"})


async def get_kb_passages(doc_id: str | None = None, intent: str | None = None, query: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_kb_passages(doc_id=doc_id, intent=intent, query=query)
    return await _get("/api/gaf/kb-passages", {"docId": doc_id, "intent": intent, "q": query})


async def get_product_approval(product: str) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_product_approval(product=product)
    return await _get("/api/gaf/product-approval", {"product": product})


async def get_warranty_rules(tier: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_warranty_rules(tier=tier)
    return await _get("/api/gaf/warranty-rules", {"tier": tier})


async def get_escalation_rules() -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_escalation_rules()
    return await _get("/api/gaf/escalation-rules", {})


async def get_warehouses(warehouse_id: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_warehouses(warehouse_id=warehouse_id)
    return await _get("/api/gaf/warehouses", {"warehouseId": warehouse_id})


async def get_add_on_rules() -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_add_on_rules()
    return await _get("/api/gaf/add-on-rules", {})


async def get_discounts(on_date: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_discounts(on_date=on_date)
    return await _get("/api/gaf/discounts", {"date": on_date})


async def get_contractors(zip_code: str | None = None, city: str | None = None, radius_miles: float = 25.0,
                          limit: int = 10, min_tier: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_contractors(zip_code=zip_code, city=city, radius_miles=radius_miles, limit=limit, min_tier=min_tier)
    return await _get("/api/gaf/contractors", {"zip": zip_code, "city": city, "radius": radius_miles, "limit": limit, "minTier": min_tier})


async def get_zip(zip_code: str) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_zip(zip_code=zip_code)
    return await _get("/api/gaf/zips", {"zip": zip_code})


async def get_counties(region_id: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_counties(region_id=region_id)
    return await _get("/api/gaf/counties", {"regionId": region_id})


async def get_sales_reps(rep_id: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_sales_reps(rep_id=rep_id)
    return await _get("/api/gaf/sales-reps", {"repId": rep_id})


async def get_emails(email_id: str | None = None, account_id: str | None = None, rep_id: str | None = None) -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_emails(email_id=email_id, account_id=account_id, rep_id=rep_id)
    return await _get("/api/gaf/emails", {"emailId": email_id, "accountId": account_id, "repId": rep_id})


async def get_use_cases() -> ToolResult:
    if DATA_SOURCE == "local":
        return await _local().get_use_cases()
    return await _get("/api/gaf/use-cases", {})
