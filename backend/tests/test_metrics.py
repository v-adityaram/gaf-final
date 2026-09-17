"""AI Metrics & Order History through the real HTTP endpoints (storage is
redirected to a temp dir by conftest). The orchestrators are mocked with
canned results: these tests are about capture/aggregation/filtering/
persistence and, above all, that an order counts as CONFIRMED only after a
successful /api/order/confirm -- never from validation, a ready-for-review
status, or a session merely existing."""

from fastapi.testclient import TestClient

from app.foundry_client import FoundryCallError
from app.main import app
from app.orchestrators import order_orchestrator, warranty_orchestrator
from app.services import metrics_service, order_service

client = TestClient(app)


def _order_result(status, *, duplicate="PASSED", inventory="PASSED", credit="PASSED"):
    result = {
        "status": status, "agent_message": "order review", "agent_timeline": ["step"], "model": "gpt-5-mini",
        "guardrails": [{"key": "credit_check", "label": "Credit checked against order total", "status": credit}],
        "order_details": {
            "customer_id": "ACC-1001", "customer_name": "Tampa Contractor Group 01", "sku": "TL-HDZ-01", "product": "Timberline HDZ Shingles",
            "quantity": 12, "unit": "squares", "delivery_city": "Tampa", "sales_rep_id": "REP-001", "total_squares": 12,
            "lines": [{"sku": "TL-HDZ-01", "included": True}, {"sku": "COBRA-RIDGE", "included": False}],
            "pricing": {"subtotal": 1422.0, "discount_total": 0.0, "total": 1422.0, "discounts": [], "commission": {"rate": 0.03, "amount": 42.66}},
            "customer_match_status": "PASSED", "product_match_status": "PASSED",
            "credit_check_status": credit, "inventory_check_status": inventory, "duplicate_check_status": duplicate,
            "checks": [{"name": "Credit Check", "status": credit}, {"name": "Duplicate Check", "status": duplicate, "details": {"duplicate_order_id": "ORD-77001" if duplicate == "WARNING" else None}}],
        },
    }
    if status == "ready_for_review":
        result["order_session_id"] = order_service.create_session(result)
    return result


def _mock_order(monkeypatch, **kwargs):
    async def fake_run(message, history=None):
        return _order_result(**kwargs)

    monkeypatch.setattr(order_orchestrator, "run_order_chat", fake_run)


def test_order_request_and_order_history_are_recorded_with_real_latency(monkeypatch):
    _mock_order(monkeypatch, status="ready_for_review")
    body = client.post("/api/order/chat", json={"message": "12 squares Timberline HDZ Charcoal for Sunshine"}).json()

    req = client.get("/api/metrics/requests").json()["requests"][0]
    assert (req["request_type"], req["status"], req["model_name"]) == ("Smart Order", "ready_for_review", "gpt-5-mini")
    assert req["total_latency_ms"] is not None and req["total_latency_ms"] >= 0
    assert req["input_tokens"] is None and req["total_tokens"] is None  # never fabricated
    assert req["guardrails"] == [{"key": "credit_check", "label": "Credit checked against order total", "status": "PASSED"}]

    order = client.get("/api/metrics/orders").json()["orders"][0]
    assert order["order_session_id"] == body["order_session_id"]
    assert order["final_status"] == "READY FOR HUMAN REVIEW" and order["confirmation_time"] is None
    assert order["line_count"] == 1 and order["order_total"] == 1422.0 and order["sales_rep_id"] == "REP-001"


def test_warning_and_blocked_orders_are_bucketed_and_filterable(monkeypatch):
    _mock_order(monkeypatch, status="ready_for_review", duplicate="WARNING")
    client.post("/api/order/chat", json={"message": "dup"})
    _mock_order(monkeypatch, status="blocked", credit="BLOCKED")
    blocked = client.post("/api/order/chat", json={"message": "blocked"}).json()
    assert blocked.get("order_session_id") is None

    orders = client.get("/api/metrics/orders").json()["orders"]
    assert [o["final_status"] for o in orders] == ["BLOCKED", "WARNING"]
    assert orders[0]["order_session_id"] is None
    assert len(client.get("/api/metrics/orders", params={"status": "WARNING"}).json()["orders"]) == 1
    assert len(client.get("/api/metrics/orders", params={"status": "BLOCKED"}).json()["orders"]) == 1
    summary = client.get("/api/metrics/summary").json()
    assert (summary["total_orders"], summary["warning_orders"], summary["blocked_orders"], summary["confirmed_orders"]) == (2, 1, 1, 0)


def test_confirmed_count_moves_only_after_a_successful_confirm(monkeypatch):
    _mock_order(monkeypatch, status="ready_for_review")
    before = client.get("/api/metrics/summary").json()["confirmed_orders"]
    session_id = client.post("/api/order/chat", json={"message": "order"}).json()["order_session_id"]
    assert client.get("/api/metrics/summary").json()["confirmed_orders"] == before

    confirm = client.post("/api/order/confirm", json={"order_session_id": session_id, "duplicate_acknowledged": False})
    assert confirm.json()["status"] == "confirmed"

    summary = client.get("/api/metrics/summary").json()
    assert summary["confirmed_orders"] == before + 1
    record = next(o for o in client.get("/api/metrics/orders").json()["orders"] if o["order_session_id"] == session_id)
    assert record["final_status"] == "CONFIRMED" and record["confirmation_time"] is not None
    assert any(c["name"] == "Human Confirmation" and c["status"] == "CONFIRMED" for c in record["checks"])
    assert [o["order_session_id"] for o in client.get("/api/metrics/orders", params={"status": "CONFIRMED"}).json()["orders"]] == [session_id]

    # A rejected confirm (duplicate not acknowledged) changes nothing.
    _mock_order(monkeypatch, status="ready_for_review", duplicate="WARNING")
    dup_session = client.post("/api/order/chat", json={"message": "dup"}).json()["order_session_id"]
    assert client.post("/api/order/confirm", json={"order_session_id": dup_session}).json()["status"] == "error"
    assert client.get("/api/metrics/summary").json()["confirmed_orders"] == before + 1


def test_warranty_and_failed_requests_are_recorded(monkeypatch):
    async def fake_warranty(question, location=None, history=None):
        return {"status": "answered", "answer": "x", "sources": [], "agent_timeline": [], "model": "gpt-5-mini", "guardrails": [{"key": "confidence_gate", "label": "ok", "status": "PASSED"}]}

    monkeypatch.setattr(warranty_orchestrator, "run_warranty_chat", fake_warranty)
    assert client.post("/api/warranty/chat", json={"question": "What does WindProven need?"}).status_code == 200

    async def fake_run(message, history=None):
        raise FoundryCallError("simulated Foundry outage")

    monkeypatch.setattr(order_orchestrator, "run_order_chat", fake_run)
    assert client.post("/api/order/chat", json={"message": "order"}).status_code == 502

    requests = client.get("/api/metrics/requests").json()["requests"]
    assert [r["status"] for r in requests] == ["failed", "answered"]
    assert client.get("/api/metrics/requests", params={"request_type": "Warranty"}).json()["requests"][0]["guardrails"][0]["key"] == "confidence_gate"
    summary = client.get("/api/metrics/summary").json()
    assert (summary["total_requests"], summary["warranty_requests"], summary["failed_requests"], summary["successful_requests"]) == (2, 1, 1, 1)
    assert summary["active_model"] == "gpt-5-mini" and summary["average_latency_ms"] is not None


def test_history_persists_across_a_simulated_restart():
    metrics_service.record_request(request_type="Smart Order", user_request="persisted request", status="ready_for_review", total_latency_ms=12.5)
    session_id = order_service.create_session({"status": "ready_for_review", "order_details": {"credit_check_status": "PASSED", "duplicate_check_status": "PASSED"}})
    metrics_service.record_order({"status": "ready_for_review", "order_session_id": session_id, "order_details": {"credit_check_status": "PASSED", "duplicate_check_status": "PASSED"}})
    order_service.confirm_session(session_id)
    metrics_service.confirm_order(session_id)

    # "Restart" == nothing is cached in memory; every read re-parses the files.
    assert any(r["user_request"] == "persisted request" for r in metrics_service.get_requests())
    record = next(r for r in metrics_service.get_orders() if r["order_session_id"] == session_id)
    assert record["final_status"] == "CONFIRMED" and record["confirmation_time"] is not None
