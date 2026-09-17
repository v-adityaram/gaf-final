"""The append-only human-review queue behind low-confidence warranty
answers (storage redirected to tmp_path by conftest)."""

from app.services import review_queue


def test_threshold_is_95():
    assert review_queue.AUTO_ANSWER_THRESHOLD == 95


def test_enqueue_then_list_then_resolve_keeps_an_audit_trail():
    item = review_queue.enqueue(question="q?", draft_answer="draft", confidence=70, reasons=["r"], sources=[{"document_id": "DOC-102"}], location=None)
    assert item["review_id"].startswith("RV-")
    assert item["status"] == "pending"

    pending = review_queue.list_reviews(status="pending")
    assert [r["review_id"] for r in pending] == [item["review_id"]]

    resolved = review_queue.resolve(item["review_id"], "edit", "final text", "reviewer@example")
    assert resolved["status"] == "resolved"
    assert resolved["final_answer"] == "final text"
    assert resolved["reviewer"] == "reviewer@example"

    # The latest record wins in the listing, and the file holds both lines.
    assert review_queue.list_reviews(status="pending") == []
    assert review_queue.list_reviews()[0]["status"] == "resolved"
    assert review_queue.REVIEW_FILE.read_text(encoding="utf-8").count("\n") == 2


def test_resolve_defaults_final_answer_to_the_draft_and_unknown_id_is_none():
    item = review_queue.enqueue(question="q?", draft_answer="draft", confidence=50, reasons=[], sources=[], location="Tampa")
    assert review_queue.resolve(item["review_id"], "approve", None, None)["final_answer"] == "draft"
    assert review_queue.resolve("RV-NOPE", "approve", None, None) is None
