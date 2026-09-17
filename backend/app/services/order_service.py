import uuid
from typing import Any, Optional

from app.services import confirmed_orders_store

# In-memory demo session store. No real ERP/database — this is intentional
# per the prototype scope (never auto-submit, never call a real ERP). The
# Smart Order Agent's LLM reasoning is never trusted to submit an order on
# its own; a human always has to click Confirm here.
_SESSIONS: dict[str, dict[str, Any]] = {}


def create_session(order_result: dict[str, Any]) -> str:
    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = {**order_result, "confirmed": False}
    return session_id


def get_session(session_id: str) -> Optional[dict[str, Any]]:
    return _SESSIONS.get(session_id)


def confirm_session(session_id: str, duplicate_acknowledged: bool = False) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if session is None:
        return {"status": "error", "message": "Unknown order session."}

    if session.get("confirmed"):
        return {"status": "error", "message": "Order was already confirmed."}

    details = session.get("order_details") or {}

    # Credit hold hard block -- defense in depth. A BLOCKED order never gets
    # a session id in the first place (order_orchestrator only creates one
    # for READY FOR HUMAN REVIEW), so this should be unreachable in normal
    # use, but a client can never talk this endpoint into confirming a
    # credit-hold order by any means, including a stale/tampered request.
    if details.get("credit_check_status") == "BLOCKED":
        return {"status": "error", "message": "This order is on credit hold and cannot be confirmed."}

    # Duplicate order guard -- the customer must explicitly acknowledge a
    # detected duplicate before this can go through. duplicate_acknowledged
    # is a real gate here, not just a value that gets stored.
    if details.get("duplicate_check_status") == "WARNING" and not duplicate_acknowledged:
        return {
            "status": "error",
            "message": "A possible duplicate order was detected. Please acknowledge the duplicate warning before confirming.",
        }

    session["confirmed"] = True
    session["duplicate_acknowledged"] = duplicate_acknowledged

    # The one and only place a confirmation is ever persisted -- reached
    # only after both guards above have passed. Never called for
    # READY FOR HUMAN REVIEW/WARNING/BLOCKED/NEEDS CLARIFICATION: those
    # statuses never reach this line.
    record = confirmed_orders_store.record_confirmation(session_id, details, duplicate_acknowledged=duplicate_acknowledged)

    return {
        "status": "confirmed",
        "message": "Order confirmed.",
        "erp_submission": "simulated",
        "confirmation": record,
    }


def reset_all() -> None:
    _SESSIONS.clear()
