"""The persistent confirmed-order ledger (data/orders/confirmed_orders.json,
redirected to tmp_path) only ever gets a record from a real, successful
confirm -- never from validation, ready-for-review status, or a session
merely existing -- and survives duplicates, restarts and corruption."""

from fastapi.testclient import TestClient

from app.main import app
from app.orchestrators import order_orchestrator
from app.services import confirmed_orders_store, order_service

client = TestClient(app)


def _order_details(**overrides):
    details = {
        "customer_id": "ACC-1001", "customer_name": "Tampa Contractor Group 01", "trade_name": "Sunshine Roofing Supply", "sales_rep_id": "REP-001",
        "sku": "TL-HDZ-01", "product": "Timberline HDZ Shingles", "colour": "Charcoal", "quantity": 12, "unit": "squares", "total_squares": 12,
        "lines": [
            {"sku": "TL-HDZ-01", "product": "Timberline HDZ Shingles", "colour": "Charcoal", "quantity": 12, "unit": "squares", "unit_price": 39.5, "line_subtotal": 1422.0, "source": "customer", "included": True},
            {"sku": "COBRA-RIDGE", "product": "Cobra Ridge Ventilation", "colour": None, "quantity": 4, "unit": "pieces", "unit_price": 19.0, "line_subtotal": 76.0, "source": "add_on", "included": False},
        ],
        "pricing": {"subtotal": 1422.0, "discount_total": 56.88, "total": 1365.12, "discounts": [{"name": "Fall promo"}], "commission": {"rate": 0.03, "amount": 40.95}},
        "delivery_city": "Tampa", "delivery_date": "next Tuesday", "delivery_date_resolved": "2026-09-22", "delivery_method": "job site",
        "credit_check_status": "PASSED", "inventory_check_status": "PASSED", "duplicate_check_status": "PASSED",
        "checks": [{"name": "Duplicate Check", "status": "PASSED", "details": {"duplicate_order_id": None, "duplicate_order_count": 0}}],
    }
    details.update(overrides)
    return details


def _mock(monkeypatch, status="ready_for_review", **overrides):
    async def fake_run(message, history=None):
        result = {"status": status, "agent_message": "review", "agent_timeline": [], "order_details": _order_details(**overrides)}
        if status == "ready_for_review":
            result["order_session_id"] = order_service.create_session(result)
        return result

    monkeypatch.setattr(order_orchestrator, "run_order_chat", fake_run)


def test_non_confirmed_statuses_never_create_a_file_entry(monkeypatch):
    _mock(monkeypatch)
    assert client.post("/api/order/chat", json={"message": "order"}).json()["status"] == "ready_for_review"
    _mock(monkeypatch, status="blocked", credit_check_status="BLOCKED")
    assert client.post("/api/order/chat", json={"message": "order"}).json()["status"] == "blocked"
    _mock(monkeypatch, duplicate_check_status="WARNING")
    client.post("/api/order/chat", json={"message": "order"})
    assert confirmed_orders_store.count_confirmed_orders() == 0
    assert confirmed_orders_store.get_confirmed_orders() == []
    assert confirmed_orders_store.CONFIRMED_ORDERS_FILE.exists() is False


def test_confirmation_creates_exactly_one_record_with_pricing_and_lines(monkeypatch):
    _mock(monkeypatch)
    session_id = client.post("/api/order/chat", json={"message": "order"}).json()["order_session_id"]
    confirm = client.post("/api/order/confirm", json={"order_session_id": session_id, "duplicate_acknowledged": False})
    assert confirm.json()["status"] == "confirmed"

    records = confirmed_orders_store.get_confirmed_orders()
    assert len(records) == 1
    r = records[0]
    assert r["order_session_id"] == session_id and r["final_status"] == "CONFIRMED" and r["confirmation_id"] and r["confirmed_at"]
    assert (r["customer_id"], r["trade_name"], r["sales_rep_id"], r["sku"], r["color"]) == ("ACC-1001", "Sunshine Roofing Supply", "REP-001", "TL-HDZ-01", "Charcoal")
    assert [l["sku"] for l in r["lines"]] == ["TL-HDZ-01"]  # unticked add-ons are not part of the confirmed order
    assert (r["order_subtotal"], r["discount_total"], r["order_total"], r["discounts"]) == (1422.0, 56.88, 1365.12, ["Fall promo"])
    assert (r["commission_rate"], r["commission_amount"]) == (0.03, 40.95)
    assert r["delivery_date"] == "2026-09-22" and r["delivery_method"] == "job site"
    assert r["duplicate_warning"] is False and r["duplicate_order_id"] is None
    assert confirm.json()["confirmation"] == r
    assert client.get("/api/orders/confirmed").json()["confirmed_orders"] == [r]


def test_idempotent_per_session_and_duplicate_details_are_recorded(monkeypatch):
    _mock(monkeypatch, duplicate_check_status="WARNING", checks=[{"name": "Duplicate Check", "status": "WARNING", "details": {"duplicate_order_id": "ORD-77005", "duplicate_order_count": 1}}])
    session_id = client.post("/api/order/chat", json={"message": "order"}).json()["order_session_id"]
    assert client.post("/api/order/confirm", json={"order_session_id": session_id, "duplicate_acknowledged": False}).json()["status"] == "error"
    assert confirmed_orders_store.count_confirmed_orders() == 0

    first = client.post("/api/order/confirm", json={"order_session_id": session_id, "duplicate_acknowledged": True}).json()
    assert first["status"] == "confirmed"
    record = confirmed_orders_store.get_confirmed_orders()[0]
    assert record["duplicate_warning"] is True and record["duplicate_order_id"] == "ORD-77005" and record["duplicate_acknowledged"] is True

    # Same session again -- order_service refuses, and even a direct store call returns the existing record.
    assert client.post("/api/order/confirm", json={"order_session_id": session_id, "duplicate_acknowledged": True}).json()["status"] == "error"
    assert confirmed_orders_store.record_confirmation(session_id, _order_details()) == record
    assert confirmed_orders_store.count_confirmed_orders() == 1


def test_missing_empty_or_corrupted_file_reads_as_empty_and_self_heals():
    assert confirmed_orders_store.get_confirmed_orders() == []
    confirmed_orders_store.ORDERS_DIR.mkdir(parents=True, exist_ok=True)
    confirmed_orders_store.CONFIRMED_ORDERS_FILE.write_text("", encoding="utf-8")
    assert confirmed_orders_store.get_confirmed_orders() == []
    confirmed_orders_store.CONFIRMED_ORDERS_FILE.write_text("{not valid json", encoding="utf-8")
    assert confirmed_orders_store.count_confirmed_orders() == 0

    record = confirmed_orders_store.record_confirmation("session-after-corruption", _order_details())
    assert record["order_session_id"] == "session-after-corruption"
    assert confirmed_orders_store.count_confirmed_orders() == 1  # the next write repairs the file
    assert confirmed_orders_store.get_confirmed_orders(limit=1)[0]["order_session_id"] == "session-after-corruption"
