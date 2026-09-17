import pytest

from app.services import confirmed_orders_store, metrics_service, order_service, review_queue


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path, monkeypatch):
    """Every test that hits an endpoint touching metrics_service (order/
    warranty/assistant/voice chat, order confirm) writes real request/order
    history rows. Without this, running the test suite would pollute the
    actual data/metrics/*.jsonl files the AI Metrics & Order History
    dashboard reads from with synthetic test data. Redirect storage to a
    throwaway per-test directory instead."""
    metrics_dir = tmp_path / "metrics"
    monkeypatch.setattr(metrics_service, "METRICS_DIR", metrics_dir)
    monkeypatch.setattr(metrics_service, "REQUESTS_FILE", metrics_dir / "request_history.jsonl")
    monkeypatch.setattr(metrics_service, "ORDERS_FILE", metrics_dir / "order_history.jsonl")

    # Same isolation for the confirmed-orders ledger -- a real confirm call
    # in a test would otherwise append to the actual
    # data/orders/confirmed_orders.json a stakeholder demo reads from.
    orders_dir = tmp_path / "orders"
    monkeypatch.setattr(confirmed_orders_store, "ORDERS_DIR", orders_dir)
    monkeypatch.setattr(confirmed_orders_store, "CONFIRMED_ORDERS_FILE", orders_dir / "confirmed_orders.json")

    # And for the warranty human-review queue (data/review_queue/*.jsonl),
    # which every low-confidence warranty answer appends to.
    review_dir = tmp_path / "review_queue"
    monkeypatch.setattr(review_queue, "REVIEW_DIR", review_dir)
    monkeypatch.setattr(review_queue, "REVIEW_FILE", review_dir / "warranty_reviews.jsonl")

    # In-memory order sessions never leak between tests.
    order_service.reset_all()
    yield
    order_service.reset_all()
