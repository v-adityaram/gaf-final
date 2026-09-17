import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import voice
from app.config import CORS_ORIGINS, FOUNDRY_CONFIGURED, GAF_DATA_SOURCE, VOICE_CONFIGURED
from app.foundry_client import FoundryCallError, FoundryNotConfiguredError
from app.models import (
    AssistantChatRequest,
    AssistantChatResponse,
    EmailDraftRequest,
    EmailDraftResponse,
    EmailIntakeRequest,
    EmailIntakeResponse,
    FeedbackRequest,
    FeedbackResponse,
    FeedbackSummary,
    OrderChatRequest,
    OrderChatResponse,
    OrderConfirmRequest,
    OrderConfirmResponse,
    OrderRecheckRequest,
    PhotoRequest,
    PhotoResponse,
    ReviewResolveRequest,
    WarrantyChatRequest,
    WarrantyChatResponse,
)
from app.orchestrators import (
    assistant_orchestrator,
    contractor_orchestrator,
    email_orchestrator,
    order_orchestrator,
    photo_orchestrator,
    recap_orchestrator,
    warranty_orchestrator,
)
from app.services import confirmed_orders_store, feedback_service, gaf_api_client, metrics_service, order_service, review_queue

logger = logging.getLogger("gaf_demo.main")

app = FastAPI(title="GAF Sales Assistant Prototype")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice.router)


# Secret/error guard: a raw exception message can echo request/response
# internals that have no business reaching a browser. Every Foundry-call
# failure is logged in full server-side and only a fixed, generic message
# crosses the wire.
def _safe_detail(exc: Exception) -> str:
    logger.warning("foundry_call_failed: %s", exc)
    if isinstance(exc, FoundryNotConfiguredError):
        return "The AI service is not configured. Please contact an administrator."
    return "The AI service is temporarily unavailable. Please try again."


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})


def _history(request) -> list[dict]:
    return [turn.model_dump() for turn in request.history]


def _catalog_or_404(result, key: str | None = None):
    if not result.success:
        detail = (result.data or {}).get("supportMessage") or "Not found"
        raise HTTPException(status_code=result.status_code or 404, detail=detail)
    data = (result.data or {}).get("data", {})
    return data[key] if key else data


@app.get("/api/health")
def health():
    return {"status": "ok", "foundry_configured": FOUNDRY_CONFIGURED, "voice_configured": VOICE_CONFIGURED, "data_source": GAF_DATA_SOURCE}


# ----------------------------------------------------------------- orders

@app.post("/api/order/chat", response_model=OrderChatResponse)
async def order_chat(request: OrderChatRequest):
    started_at = metrics_service.start_timer()
    try:
        result = await order_orchestrator.run_order_chat(request.message, _history(request))
        metrics_service.record_request(request_type="Smart Order", user_request=request.message, status=result.get("status", "unknown"),
                                       model_name=result.get("model"), total_latency_ms=metrics_service.elapsed_ms(started_at), guardrails=result.get("guardrails"))
        metrics_service.record_order(result)
        return result
    except FoundryNotConfiguredError as exc:
        metrics_service.record_request(request_type="Smart Order", user_request=request.message, status="failed", total_latency_ms=metrics_service.elapsed_ms(started_at))
        raise HTTPException(status_code=503, detail=_safe_detail(exc)) from exc
    except FoundryCallError as exc:
        metrics_service.record_request(request_type="Smart Order", user_request=request.message, status="failed", total_latency_ms=metrics_service.elapsed_ms(started_at))
        raise HTTPException(status_code=502, detail=_safe_detail(exc)) from exc


def _recheck_fields(request: OrderRecheckRequest) -> dict:
    if request.lines:
        items = [{
            "sku": l.sku, "productDescription": l.product, "colour": l.colour, "quantity": l.quantity, "unit": l.unit,
            "included": l.included, "source": l.source, "add_on_rule": l.add_on_rule,
        } for l in request.lines]
    else:
        items = [{"sku": request.sku, "productDescription": request.product, "colour": request.colour, "quantity": request.quantity, "unit": request.unit}]
    return {
        "customerNameOrAlias": request.customer_id or request.customer_name,
        "items": items,
        "includeAddOns": request.include_add_ons,
        "deliveryCity": request.delivery_city,
        "deliveryDate": request.delivery_date,
        "deliveryMethod": request.delivery_method,
    }


@app.post("/api/order/recheck", response_model=OrderChatResponse)
async def order_recheck(request: OrderRecheckRequest):
    started_at = metrics_service.start_timer()
    result = await order_orchestrator.run_order_recheck(_recheck_fields(request), _history(request))
    first = request.lines[0] if request.lines else None
    summary = f"{(first.quantity if first else request.quantity) or '?'} {(first.unit if first else request.unit) or ''} {(first.product or first.sku) if first else request.product or ''} for {request.customer_name or request.customer_id or '?'}".strip()
    metrics_service.record_request(request_type="Smart Order", user_request=f"Recheck: {summary}", status=result.get("status", "unknown"),
                                   model_name=result.get("model"), total_latency_ms=metrics_service.elapsed_ms(started_at), guardrails=result.get("guardrails"))
    metrics_service.record_order(result)
    return result


@app.post("/api/order/confirm", response_model=OrderConfirmResponse)
def confirm_order(request: OrderConfirmRequest):
    result = order_service.confirm_session(request.order_session_id, request.duplicate_acknowledged)
    if result.get("status") == "confirmed":
        metrics_service.confirm_order(request.order_session_id)
    return result


# --------------------------------------------------------------- warranty

@app.post("/api/warranty/chat", response_model=WarrantyChatResponse)
async def warranty_chat(request: WarrantyChatRequest):
    started_at = metrics_service.start_timer()
    try:
        result = await warranty_orchestrator.run_warranty_chat(request.question, request.location, _history(request))
        metrics_service.record_request(request_type="Warranty", user_request=request.question, status=result.get("status", "unknown"),
                                       model_name=result.get("model"), total_latency_ms=metrics_service.elapsed_ms(started_at), guardrails=result.get("guardrails"))
        return result
    except FoundryNotConfiguredError as exc:
        metrics_service.record_request(request_type="Warranty", user_request=request.question, status="failed", total_latency_ms=metrics_service.elapsed_ms(started_at))
        raise HTTPException(status_code=503, detail=_safe_detail(exc)) from exc
    except FoundryCallError as exc:
        metrics_service.record_request(request_type="Warranty", user_request=request.question, status="failed", total_latency_ms=metrics_service.elapsed_ms(started_at))
        raise HTTPException(status_code=502, detail=_safe_detail(exc)) from exc


@app.get("/api/reviews")
def reviews(status: str | None = None, limit: int = 100):
    return {"reviews": review_queue.list_reviews(status=status, limit=limit), "threshold": review_queue.AUTO_ANSWER_THRESHOLD}


@app.post("/api/reviews/{review_id}/resolve")
def resolve_review(review_id: str, request: ReviewResolveRequest):
    if request.decision not in ("approve", "edit", "reject"):
        raise HTTPException(status_code=400, detail="decision must be approve, edit or reject")
    record = review_queue.resolve(review_id, request.decision, request.final_answer, request.reviewer)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown review id")
    return record


# ------------------------------------------------------------- assistant

_REQUEST_TYPE = {"order": "Smart Order", "warranty": "Warranty", "general": "Assistant", "contractor": "Contractor"}


@app.post("/api/assistant/chat", response_model=AssistantChatResponse, response_model_by_alias=True)
async def assistant_chat(request: AssistantChatRequest):
    started_at = metrics_service.start_timer()
    try:
        result = await assistant_orchestrator.run_assistant_chat(request.message, request.location, _history(request))
        metrics_service.record_request(request_type=_REQUEST_TYPE.get(result.get("routed_to"), "Assistant"), user_request=request.message,
                                       status=result.get("status", "unknown"), model_name=result.get("model"),
                                       total_latency_ms=metrics_service.elapsed_ms(started_at), guardrails=result.get("guardrails"))
        if result.get("routed_to") == "order":
            metrics_service.record_order(result)
        return result
    except FoundryNotConfiguredError as exc:
        metrics_service.record_request(request_type="Assistant", user_request=request.message, status="failed", total_latency_ms=metrics_service.elapsed_ms(started_at))
        raise HTTPException(status_code=503, detail=_safe_detail(exc)) from exc
    except FoundryCallError as exc:
        metrics_service.record_request(request_type="Assistant", user_request=request.message, status="failed", total_latency_ms=metrics_service.elapsed_ms(started_at))
        raise HTTPException(status_code=502, detail=_safe_detail(exc)) from exc


@app.post("/api/assistant/draft-email", response_model=EmailDraftResponse)
async def assistant_draft_email(request: EmailDraftRequest):
    started_at = metrics_service.start_timer()
    rep = None
    if request.rep_id:
        res = await gaf_api_client.get_sales_reps(rep_id=request.rep_id)
        rep = ((res.data or {}).get("data", {}).get("salesReps") or [None])[0] if res.success else None
    try:
        result = recap_orchestrator.run_recap(_history(request), rep)
        metrics_service.record_request(request_type="Email Draft", user_request="Customer email drafted", status="answered", total_latency_ms=metrics_service.elapsed_ms(started_at))
        return result
    except FoundryNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=_safe_detail(exc)) from exc
    except FoundryCallError as exc:
        raise HTTPException(status_code=502, detail=_safe_detail(exc)) from exc


@app.post("/api/assistant/recap", response_model=EmailDraftResponse, include_in_schema=False)
async def assistant_recap(request: EmailDraftRequest):
    return await assistant_draft_email(request)


@app.post("/api/assistant/photo", response_model=PhotoResponse)
async def assistant_photo(request: PhotoRequest):
    started_at = metrics_service.start_timer()
    if not request.image_data_url.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="image_data_url must be a data:image/... URL")
    if len(request.image_data_url) > 6_000_000:
        raise HTTPException(status_code=413, detail="Image too large -- the browser should downscale before upload")
    try:
        result = await photo_orchestrator.run_photo_intake(request.image_data_url, request.note, request.location)
        metrics_service.record_request(request_type="Photo", user_request=request.note or "Photo submitted", status=result.get("status", "unknown"), total_latency_ms=metrics_service.elapsed_ms(started_at))
        return result
    except FoundryNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=_safe_detail(exc)) from exc
    except FoundryCallError as exc:
        raise HTTPException(status_code=502, detail=_safe_detail(exc)) from exc


# ------------------------------------------------------------ email agent

@app.get("/api/inbox")
async def inbox(rep_id: str | None = None, account_id: str | None = None):
    res = await gaf_api_client.get_emails(rep_id=rep_id, account_id=account_id)
    return {"emails": _catalog_or_404(res, "emails")}


@app.post("/api/email/intake", response_model=EmailIntakeResponse)
async def email_intake(request: EmailIntakeRequest):
    started_at = metrics_service.start_timer()
    try:
        result = await email_orchestrator.run_email_intake(request.email_ids, request.location, _history(request))
        for item in result["items"]:
            r = item.get("result") or {}
            metrics_service.record_request(request_type="Email", user_request=item.get("request") or item["email_id"], status=r.get("status", item["status"]),
                                           model_name=r.get("model"), total_latency_ms=metrics_service.elapsed_ms(started_at), guardrails=r.get("guardrails"))
            if r.get("routed_to") == "order":
                metrics_service.record_order(r)
        return result
    except FoundryNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=_safe_detail(exc)) from exc
    except FoundryCallError as exc:
        raise HTTPException(status_code=502, detail=_safe_detail(exc)) from exc


# ------------------------------------------------------------ contractors

@app.get("/api/contractors")
async def contractors(zip: str | None = None, city: str | None = None, radius: float = 25.0, limit: int = 10, min_tier: str | None = None):
    res = await gaf_api_client.get_contractors(zip_code=zip, city=city, radius_miles=radius, limit=limit, min_tier=min_tier)
    return _catalog_or_404(res)


# -------------------------------------------------------------- sales reps

@app.get("/api/reps")
async def reps():
    res = await gaf_api_client.get_sales_reps()
    return {"reps": _catalog_or_404(res, "salesReps")}


@app.get("/api/reps/{rep_id}/dashboard")
async def rep_dashboard(rep_id: str):
    rep_res = await gaf_api_client.get_sales_reps(rep_id=rep_id)
    rep = _catalog_or_404(rep_res, "salesReps")[0]
    customers = _catalog_or_404(await gaf_api_client.get_customers(rep_id=rep_id), "customers")
    orders = _catalog_or_404(await gaf_api_client.get_orders(rep_id=rep_id), "orders")
    emails = _catalog_or_404(await gaf_api_client.get_emails(rep_id=rep_id), "emails")
    confirmed = [o for o in confirmed_orders_store.get_confirmed_orders() if o.get("sales_rep_id") == rep_id]
    rate = float(rep.get("commissionRate") or 0)
    booked = sum(float(o.get("totalUsd") or 0) for o in orders if o.get("status") in ("Confirmed", "Allocated", "Shipped", "Delivered"))
    session_total = sum(float(o.get("order_total") or 0) for o in confirmed)
    pipeline = sum(float(o.get("totalUsd") or 0) for o in orders if o.get("status") == "Draft")
    return {
        "rep": rep,
        "accounts": customers,
        "orders": orders,
        "confirmed_this_session": confirmed,
        "inbox_unread": sum(1 for e in emails if not e.get("read")),
        "commission": {
            "rate": rate,
            "booked_sales_usd": round(booked, 2),
            "booked_commission_usd": round(booked * rate, 2),
            "session_sales_usd": round(session_total, 2),
            "session_commission_usd": round(session_total * rate, 2),
            "pipeline_usd": round(pipeline, 2),
            "quota_usd": rep.get("quotaUsd"),
            "quota_progress": round((booked + session_total) / float(rep["quotaUsd"]), 4) if rep.get("quotaUsd") else None,
        },
    }


# ----------------------------------------------------------- demo helpers

@app.get("/api/demo/use-cases")
async def use_cases():
    return _catalog_or_404(await gaf_api_client.get_use_cases())


@app.get("/api/catalog/products")
async def catalog_products(family: str | None = None, type: str | None = None):
    return _catalog_or_404(await gaf_api_client.get_products(family=family, product_type=type))


@app.get("/api/catalog/discounts")
async def catalog_discounts(date: str | None = None):
    return _catalog_or_404(await gaf_api_client.get_discounts(on_date=date))


# ---------------------------------------------------------------- feedback

@app.post("/api/feedback", response_model=FeedbackResponse)
def feedback(request: FeedbackRequest):
    if request.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")
    feedback_id = feedback_service.record(request.model_dump())
    return {"status": "ok", "feedback_id": feedback_id}


@app.get("/api/feedback/summary", response_model=FeedbackSummary)
def feedback_summary():
    return feedback_service.summary()


# ----------------------------------------------------------------- metrics

@app.get("/api/metrics/summary")
def metrics_summary():
    return metrics_service.summary()


@app.get("/api/metrics/requests")
def metrics_requests(request_type: str | None = None, status: str | None = None, limit: int = 100):
    return {"requests": metrics_service.get_requests(request_type=request_type, status=status, limit=limit)}


@app.get("/api/metrics/orders")
def metrics_orders(status: str | None = None, limit: int = 100):
    return {"orders": metrics_service.get_orders(status=status, limit=limit)}


@app.get("/api/orders/confirmed")
def orders_confirmed(limit: int = 100, rep_id: str | None = None):
    records = confirmed_orders_store.get_confirmed_orders(limit=limit)
    if rep_id:
        records = [r for r in records if r.get("sales_rep_id") == rep_id]
    return {"confirmed_orders": records}


@app.post("/api/session/reset")
def session_reset():
    order_service.reset_all()
    return {"status": "ok", "message": "Session state cleared."}
