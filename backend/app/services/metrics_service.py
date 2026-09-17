import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import DATA_DIR
from app.services import confirmed_orders_store

METRICS_DIR = DATA_DIR / "metrics"
REQUESTS_FILE = METRICS_DIR / "request_history.jsonl"
ORDERS_FILE = METRICS_DIR / "order_history.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def start_timer() -> float:
    return time.perf_counter()


def elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def record_request(
    *,
    request_type: str,
    user_request: str,
    status: str,
    total_latency_ms: float,
    model_name: Optional[str] = None,
    model_latency_ms: Optional[float] = None,
    retrieval_latency_ms: Optional[float] = None,
    tool_latency_ms: Optional[float] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    guardrails: Optional[list[dict[str, Any]]] = None,
    request_id: Optional[str] = None,
) -> dict[str, Any]:
    record = {
        "request_id": request_id or str(uuid.uuid4()),
        "timestamp": _now(),
        "request_type": request_type,
        "user_request": user_request,
        "model_name": model_name,
        "status": status,
        "total_latency_ms": total_latency_ms,
        "model_latency_ms": model_latency_ms,
        "retrieval_latency_ms": retrieval_latency_ms,
        "tool_latency_ms": tool_latency_ms,
        # Real token usage only -- foundry_client doesn't currently surface
        # usage from the Responses API, so these stay null (-> "N/A" in the
        # UI) rather than ever being guessed.
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        # The same guardrails list the caller (order/warranty orchestrator)
        # actually computed for this turn -- see app/services/guardrails.py.
        # Only guardrails genuinely evaluated for this request appear here.
        "guardrails": guardrails or [],
    }
    _append_jsonl(REQUESTS_FILE, record)
    return record


def _status_label(status: str, details: dict[str, Any]) -> str:
    """Maps the order orchestrator's own status to the dashboard's display
    bucket. This is a display-only label for the metrics/history view -- it
    never feeds back into order_orchestrator's business logic or the
    confirm-session flow, which keep using the original status/session id
    untouched.

    A "ready for review" order that already carries a check-level WARNING
    (duplicate detected, low/insufficient stock) is surfaced as its own
    WARNING bucket so the dashboard's Warnings filter has something to show,
    per the check statuses order_orchestrator already computed -- no new
    business rule, just a finer label over an existing one.
    """
    if status == "ready_for_review":
        if details.get("duplicate_check_status") == "WARNING" or details.get("inventory_check_status") == "WARNING":
            return "WARNING"
        return "READY FOR HUMAN REVIEW"
    return {
        "blocked": "BLOCKED",
        "needs_clarification": "NEEDS CLARIFICATION",
    }.get(status, status.upper())


def record_order(order_result: dict[str, Any]) -> Optional[dict[str, Any]]:
    details = order_result.get("order_details")
    if not isinstance(details, dict):
        return None
    session_id = order_result.get("order_session_id")
    record = {
        "order_session_id": session_id,
        "timestamp": _now(),
        "confirmation_time": None,
        "customer_id": details.get("customer_id"),
        "customer_name": details.get("customer_name"),
        "sku": details.get("sku"),
        "product": details.get("product"),
        "quantity": details.get("quantity"),
        "unit": details.get("unit"),
        "delivery_city": details.get("delivery_city"),
        "line_count": len([l for l in details.get("lines") or [] if l.get("included", True)]),
        "total_squares": details.get("total_squares"),
        "order_total": (details.get("pricing") or {}).get("total"),
        "sales_rep_id": details.get("sales_rep_id"),
        "final_status": _status_label(str(order_result.get("status", "")), details),
        "credit_check_status": details.get("credit_check_status"),
        "inventory_check_status": details.get("inventory_check_status"),
        "duplicate_check_status": details.get("duplicate_check_status"),
        "customer_match_status": details.get("customer_match_status"),
        "product_match_status": details.get("product_match_status"),
        "checks": details.get("checks", []),
    }
    _append_jsonl(ORDERS_FILE, record)
    return record


def confirm_order(session_id: str) -> None:
    records = _read_jsonl(ORDERS_FILE)
    changed = False
    for record in reversed(records):
        if record.get("order_session_id") == session_id:
            record["final_status"] = "CONFIRMED"
            record["confirmation_time"] = _now()
            checks = record.setdefault("checks", [])
            checks.append({"name": "Human Confirmation", "status": "CONFIRMED", "details": {"duplicate_acknowledged": True}})
            changed = True
            break
    if changed:
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        with ORDERS_FILE.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=True) + "\n")


def get_requests(request_type: Optional[str] = None, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    records = list(reversed(_read_jsonl(REQUESTS_FILE)))
    if request_type:
        records = [r for r in records if str(r.get("request_type", "")).lower() == request_type.lower()]
    if status:
        records = [r for r in records if str(r.get("status", "")).lower() == status.lower()]
    return records[: max(1, min(limit, 500))]


def get_orders(status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    records = list(reversed(_read_jsonl(ORDERS_FILE)))
    if status:
        records = [r for r in records if str(r.get("final_status", "")).lower() == status.lower()]
    return records[: max(1, min(limit, 500))]


def _avg(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 2) if values else None


def summary() -> dict[str, Any]:
    requests = _read_jsonl(REQUESTS_FILE)
    orders = _read_jsonl(ORDERS_FILE)
    latencies = [float(r["total_latency_ms"]) for r in requests if r.get("total_latency_ms") is not None]
    token_totals = [int(r["total_tokens"]) for r in requests if r.get("total_tokens") is not None]
    successes = [r for r in requests if str(r.get("status", "")).lower() not in {"failed", "error"}]
    model_names = [r.get("model_name") for r in reversed(requests) if r.get("model_name")]

    # Authoritative counts, never from whatever the UI's current filter
    # happens to show. CONFIRMED in particular is never derived from this
    # (or any) request/order log -- it comes solely from
    # confirmed_orders_store, the one file order_service.confirm_session()
    # writes to, and only after a real successful confirmation.
    order_statuses = [str(o.get("final_status", "")).upper() for o in orders]
    confirmed_orders = confirmed_orders_store.count_confirmed_orders()
    blocked_orders = order_statuses.count("BLOCKED")

    return {
        "total_requests": len(requests),
        "average_latency_ms": _avg(latencies),
        "fastest_response_ms": min(latencies) if latencies else None,
        "slowest_response_ms": max(latencies) if latencies else None,
        "successful_requests": len(successes),
        "failed_requests": len(requests) - len(successes),
        "smart_order_requests": sum(1 for r in requests if r.get("request_type") == "Smart Order"),
        "warranty_requests": sum(1 for r in requests if r.get("request_type") == "Warranty"),
        "average_tokens": _avg([float(v) for v in token_totals]),
        "total_tokens": sum(token_totals) if token_totals else None,
        "active_model": model_names[0] if model_names else None,
        "total_orders": len(orders),
        "confirmed_orders": confirmed_orders,
        "blocked_orders": blocked_orders,
        "ready_for_review_orders": order_statuses.count("READY FOR HUMAN REVIEW"),
        "warning_orders": order_statuses.count("WARNING"),
        "recent_latency": [{"timestamp": r.get("timestamp"), "latency_ms": r.get("total_latency_ms"), "type": r.get("request_type")} for r in requests[-20:]],
    }
