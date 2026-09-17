"""order_service.confirm_session -- the only place an order can ever be
submitted. Nothing here flips "confirmed" on its own; a credit-hold
session can never be confirmed; a duplicate needs explicit acknowledgement;
a confirmation is recorded exactly once per session."""

from app.services import confirmed_orders_store, order_service


def _order_result(**detail_overrides):
    details = {
        "customer_id": "ACC-1001", "customer_name": "Tampa Contractor Group 01", "sales_rep_id": "REP-001", "sku": "TL-HDZ-01",
        "lines": [{"sku": "TL-HDZ-01", "quantity": 12, "unit": "squares", "unit_price": 39.5, "line_subtotal": 1422.0, "included": True}],
        "pricing": {"subtotal": 1422.0, "discount_total": 0.0, "total": 1422.0, "discounts": [], "commission": {"rate": 0.03, "amount": 42.66}},
        "credit_check_status": "PASSED", "duplicate_check_status": "PASSED",
    }
    details.update(detail_overrides)
    return {"status": "ready_for_review", "order_details": details}


def test_confirmation_never_happens_automatically():
    session_id = order_service.create_session(_order_result())
    assert order_service.get_session(session_id)["confirmed"] is False
    assert confirmed_orders_store.count_confirmed_orders() == 0


def test_successful_confirmation_returns_the_persisted_record():
    session_id = order_service.create_session(_order_result())
    result = order_service.confirm_session(session_id)
    assert result["status"] == "confirmed" and result["erp_submission"] == "simulated"
    record = result["confirmation"]
    assert record["order_session_id"] == session_id and record["order_total"] == 1422.0 and record["sales_rep_id"] == "REP-001"
    assert record["commission_amount"] == 42.66 and [l["sku"] for l in record["lines"]] == ["TL-HDZ-01"]
    assert order_service.get_session(session_id)["confirmed"] is True
    assert confirmed_orders_store.get_confirmed_orders() == [record]


def test_unknown_session_and_double_confirmation_are_rejected():
    assert order_service.confirm_session("not-a-real-session-id") == {"status": "error", "message": "Unknown order session."}
    session_id = order_service.create_session(_order_result())
    order_service.confirm_session(session_id)
    assert order_service.confirm_session(session_id)["status"] == "error"
    assert confirmed_orders_store.count_confirmed_orders() == 1


def test_credit_hold_session_can_never_be_confirmed_even_if_acknowledged():
    session_id = order_service.create_session(_order_result(credit_check_status="BLOCKED"))
    result = order_service.confirm_session(session_id, duplicate_acknowledged=True)
    assert result["status"] == "error" and "credit hold" in result["message"].lower()
    assert order_service.get_session(session_id)["confirmed"] is False
    assert confirmed_orders_store.count_confirmed_orders() == 0


def test_duplicate_warning_needs_explicit_acknowledgement():
    session_id = order_service.create_session(_order_result(duplicate_check_status="WARNING"))
    rejected = order_service.confirm_session(session_id, duplicate_acknowledged=False)
    assert rejected["status"] == "error" and "duplicate" in rejected["message"].lower()
    assert order_service.get_session(session_id)["confirmed"] is False

    accepted = order_service.confirm_session(session_id, duplicate_acknowledged=True)
    assert accepted["status"] == "confirmed"
    assert accepted["confirmation"]["duplicate_warning"] is True and accepted["confirmation"]["duplicate_acknowledged"] is True
