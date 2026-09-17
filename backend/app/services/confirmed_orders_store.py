"""Persistent, append-only ledger of orders that have actually been
confirmed -- the literal source of truth for "how many orders are
CONFIRMED", kept deliberately separate from data/metrics/order_history.jsonl
(which is a per-turn AI-request log covering every status, not just
confirmations).

The only writer is order_service.confirm_session() -- and only after that
function's own credit-hold hard-block and duplicate-acknowledgement guards
have already passed. Nothing here is ever written for READY FOR HUMAN
REVIEW, WARNING, BLOCKED, or NEEDS CLARIFICATION; there is no code path
into this module except a real, successful confirmation.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import DATA_DIR

logger = logging.getLogger("gaf_demo.confirmed_orders_store")

ORDERS_DIR = DATA_DIR / "orders"
CONFIRMED_ORDERS_FILE = ORDERS_DIR / "confirmed_orders.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_all() -> list[dict[str, Any]]:
    """Never raises -- a missing, empty, or corrupted file all just mean
    "no confirmed orders yet", not a crash."""
    if not CONFIRMED_ORDERS_FILE.exists():
        return []
    try:
        text = CONFIRMED_ORDERS_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("confirmed_orders_read_failed path=%s", CONFIRMED_ORDERS_FILE)
        return []
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("confirmed_orders_corrupted path=%s", CONFIRMED_ORDERS_FILE)
        return []
    return data if isinstance(data, list) else []


def _write_all(records: list[dict[str, Any]]) -> None:
    ORDERS_DIR.mkdir(parents=True, exist_ok=True)
    # Write to a temp file then atomically replace -- a crash or concurrent
    # read mid-write can never observe a half-written/corrupted file.
    tmp_path = CONFIRMED_ORDERS_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(records, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(tmp_path, CONFIRMED_ORDERS_FILE)


def record_confirmation(order_session_id: str, details: dict[str, Any], *, duplicate_acknowledged: bool = False) -> dict[str, Any]:
    """Appends exactly one record for this order_session_id. Idempotent:
    called again for a session that's already recorded (same
    order_session_id) returns the existing record instead of writing a
    duplicate -- checked before every append, per the brief's own
    "avoid duplicates" requirement."""
    records = _read_all()
    existing = next((r for r in records if r.get("order_session_id") == order_session_id), None)
    if existing is not None:
        return existing

    checks = details.get("checks") or []
    duplicate_check = next((c for c in checks if c.get("name") == "Duplicate Check"), None)
    duplicate_order_id = (duplicate_check.get("details") or {}).get("duplicate_order_id") if duplicate_check else None

    pricing = details.get("pricing") or {}
    commission = pricing.get("commission") or {}
    record = {
        "confirmation_id": str(uuid.uuid4()),
        "order_session_id": order_session_id,
        "confirmed_at": _now(),
        "customer_id": details.get("customer_id"),
        "customer_name": details.get("customer_name"),
        "trade_name": details.get("trade_name"),
        "sales_rep_id": details.get("sales_rep_id"),
        "product": details.get("product"),
        "sku": details.get("sku"),
        "color": details.get("colour"),
        "quantity": details.get("quantity"),
        "unit": details.get("unit"),
        "total_squares": details.get("total_squares"),
        "lines": [
            {"sku": l.get("sku"), "product": l.get("product"), "colour": l.get("colour"), "quantity": l.get("quantity"),
             "unit": l.get("unit"), "unit_price": l.get("unit_price"), "line_subtotal": l.get("line_subtotal"), "source": l.get("source")}
            for l in (details.get("lines") or []) if l.get("included", True)
        ],
        "order_subtotal": pricing.get("subtotal"),
        "discount_total": pricing.get("discount_total"),
        "discounts": [d.get("name") for d in pricing.get("discounts") or []],
        "order_total": pricing.get("total"),
        "commission_rate": commission.get("rate"),
        "commission_amount": commission.get("amount"),
        "delivery_city": details.get("delivery_city"),
        "delivery_date": details.get("delivery_date_resolved") or details.get("delivery_date"),
        "delivery_method": details.get("delivery_method"),
        "credit_status": details.get("credit_check_status"),
        "inventory_status": details.get("inventory_check_status"),
        "duplicate_warning": details.get("duplicate_check_status") == "WARNING",
        "duplicate_order_id": duplicate_order_id,
        "final_status": "CONFIRMED",
        "duplicate_acknowledged": duplicate_acknowledged,
    }
    records.append(record)
    _write_all(records)
    return record


def get_confirmed_orders(limit: Optional[int] = None) -> list[dict[str, Any]]:
    records = list(reversed(_read_all()))  # most recent first
    if limit is not None:
        return records[: max(1, min(limit, 500))]
    return records


def count_confirmed_orders() -> int:
    return len(_read_all())


def reset_all() -> None:
    """Dev/test utility -- clears the confirmed-orders store (mirrors
    order_service.reset_all())."""
    if CONFIRMED_ORDERS_FILE.exists():
        CONFIRMED_ORDERS_FILE.unlink()
