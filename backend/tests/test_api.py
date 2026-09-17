"""HTTP surface of app/main.py through FastAPI's TestClient. Read-only
catalogue endpoints hit the real local dataset; every model call behind
the chat endpoints is mocked by dispatching on the prompt text, so the
order -> recheck -> confirm flow runs the real orchestrators end to end."""

from fastapi.testclient import TestClient

from app import foundry_client
from app.main import app
from app.services import confirmed_orders_store, review_queue

client = TestClient(app)

ORDER_FIELDS = {
    "customerNameOrAlias": "Sunshine Roofing Supply",
    "items": [{"productDescription": "Timberline HDZ", "colour": "Charcoal", "quantity": 12, "unit": "squares"}],
    "includeAddOns": True, "deliveryCity": "Tampa", "deliveryDate": "next Tuesday", "deliveryMethod": None,
    "referenceOrderId": None, "quoteReference": False, "roofEstimate": None,
}


def _mock_llm(monkeypatch, *, route="ORDER", order_fields=ORDER_FIELDS, classification=None, synthesis="Grounded answer.\nSource: Prototype Wind Warranty Rules — vSynthetic-1"):
    def call_model_json(prompt):
        if "Decide which specialist" in prompt:
            return {"route": route, "tone": "neutral", "chat_intent": "help"}
        if "Extract fields" in prompt:
            return order_fields
        if "sorting a GAF roofing" in prompt:
            return classification or {"category": "ANSWERABLE", "product": "Timberline HDZ", "reason": "", "confidence": 0.9}
        if "Identify what this roofing-supply question" in prompt:
            return {"customerNameOrAlias": None, "productDescriptions": ["Timberline HDZ"], "orderId": None}
        if "A customer emailed" in prompt:
            return {"intent": "warranty", "request": "Gulf Coast Home Builders (ACC-1002): what do we need on a Timberline HDZ order in Naples for the WindProven warranty?", "summary": "WindProven requirements"}
        raise AssertionError(f"unexpected prompt: {prompt[:60]}")

    monkeypatch.setattr(foundry_client, "call_model_json", call_model_json)
    monkeypatch.setattr(foundry_client, "call_model", lambda prompt: synthesis)


# ------------------------------------------------------------ read-only

def test_health_reports_only_booleans_and_the_data_source():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "foundry_configured", "voice_configured", "data_source"}
    assert isinstance(body["foundry_configured"], bool) and body["data_source"] in ("local", "live")


def test_reps_and_rep_dashboard_with_commission():
    reps = client.get("/api/reps").json()["reps"]
    assert [r["repId"] for r in reps] == ["REP-001", "REP-002", "REP-003", "REP-004"]

    dash = client.get("/api/reps/REP-001/dashboard").json()
    assert dash["rep"]["name"] == "Jordan Reyes"
    assert {a["accountId"] for a in dash["accounts"]} == set(dash["rep"]["accounts"])
    assert all(o["salesRepId"] == "REP-001" for o in dash["orders"]) and dash["orders"]
    assert dash["inbox_unread"] == 4
    assert dash["confirmed_this_session"] == []
    c = dash["commission"]
    assert set(c) == {"rate", "booked_sales_usd", "booked_commission_usd", "session_sales_usd", "session_commission_usd", "pipeline_usd", "quota_usd", "quota_progress"}
    assert c["rate"] == 0.03 and c["quota_usd"] == 450000
    assert c["booked_commission_usd"] == round(c["booked_sales_usd"] * 0.03, 2)
    assert c["session_sales_usd"] == 0 and c["quota_progress"] == round(c["booked_sales_usd"] / 450000, 4)
    assert client.get("/api/reps/REP-999/dashboard").status_code == 404


def test_inbox_contractors_use_cases_and_catalog_endpoints():
    inbox = client.get("/api/inbox", params={"rep_id": "REP-001"}).json()["emails"]
    assert {e["emailId"] for e in inbox} == {"EML-001", "EML-005", "EML-007", "EML-010"}
    assert [e["emailId"] for e in client.get("/api/inbox", params={"account_id": "ACC-1015"}).json()["emails"]] == ["EML-002", "EML-006"]

    found = client.get("/api/contractors", params={"zip": "30061", "limit": 3})
    assert found.status_code == 200
    body = found.json()
    assert body["location"]["city"] == "Marietta" and len(body["contractors"]) == 3
    elite = client.get("/api/contractors", params={"zip": "30061", "min_tier": "master_elite"}).json()["contractors"]
    assert elite and all(c["certificationTier"] in ("master_elite", "presidents_club") for c in elite)
    missing = client.get("/api/contractors", params={"zip": "99999"})
    assert missing.status_code == 404 and "99999" in missing.json()["detail"]
    assert client.get("/api/contractors").status_code == 400

    use_cases = client.get("/api/demo/use-cases").json()
    assert {u["id"] for u in use_cases["useCases"]} >= {"UC-01", "UC-16"} and len(use_cases["orderScenarios"]) == 36

    products = client.get("/api/catalog/products", params={"family": "Timberline UHDZ"}).json()["products"]
    assert [p["sku"] for p in products] == ["TL-UHDZ-01"]
    discounts = client.get("/api/catalog/discounts", params={"date": "2026-12-01"}).json()
    assert discounts["asOf"] == "2026-12-01" and "DSC-SEA-WINTER" in {d["discountId"] for d in discounts["discounts"]}


# ---------------------------------------------------------------- reviews

def test_reviews_list_and_resolve():
    assert client.get("/api/reviews").json() == {"reviews": [], "threshold": 95}
    item = review_queue.enqueue(question="q", draft_answer="d", confidence=60, reasons=[], sources=[], location=None)
    listed = client.get("/api/reviews", params={"status": "pending"}).json()["reviews"]
    assert [r["review_id"] for r in listed] == [item["review_id"]]

    assert client.post(f"/api/reviews/{item['review_id']}/resolve", json={"decision": "maybe"}).status_code == 400
    assert client.post("/api/reviews/RV-NOPE/resolve", json={"decision": "approve"}).status_code == 404
    resolved = client.post(f"/api/reviews/{item['review_id']}/resolve", json={"decision": "approve", "reviewer": "lead"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved" and resolved.json()["final_answer"] == "d"
    assert client.get("/api/reviews", params={"status": "pending"}).json()["reviews"] == []


# ------------------------------------------------------- order end to end

def test_order_chat_recheck_and_confirm_end_to_end(monkeypatch):
    _mock_llm(monkeypatch)
    chat = client.post("/api/order/chat", json={"message": "12 squares Timberline HDZ Charcoal for Sunshine Roofing Supply with add-ons, Tampa next Tuesday"})
    assert chat.status_code == 200
    body = chat.json()
    assert body["status"] == "ready_for_review" and body["order_session_id"]
    assert body["provider"] == "foundry"
    details = body["order_details"]
    assert details["sku"] == "TL-HDZ-01" and details["converted_quantity"] == 36
    assert details["pricing"]["included_line_count"] == 6
    assert {c["name"] for c in details["checks"]} == {"Customer Match", "Product Match", "Pricing", "Credit Check", "Inventory Check", "Duplicate Check"}
    assert len(body["products"]) == 6

    # The rep unticks the ridge vent and changes the quantity on the form -> recheck without any model call.
    monkeypatch.setattr(foundry_client, "call_model_json", lambda prompt: (_ for _ in ()).throw(AssertionError("recheck must not call the model")))
    lines = [{"sku": l["sku"], "product": l["product"], "colour": l["colour"], "quantity": l["quantity"], "unit": l["unit"],
              "included": l["included"] and l["sku"] != "COBRA-RIDGE", "source": l["source"], "add_on_rule": l["add_on_rule"]} for l in details["lines"]]
    lines[0]["quantity"] = 10
    recheck = client.post("/api/order/recheck", json={"customer_id": "ACC-1001", "customer_name": details["customer_name"], "lines": lines,
                                                      "include_add_ons": True, "delivery_city": "Tampa", "delivery_date": "next Tuesday", "delivery_method": "job site"})
    assert recheck.status_code == 200
    rb = recheck.json()
    assert rb["status"] == "ready_for_review" and rb["model"] is None and rb["provider"] is None
    rd = rb["order_details"]
    assert rd["converted_quantity"] == 30 and rd["pricing"]["included_line_count"] == 5
    assert "COBRA-RIDGE" not in {l["sku"] for l in rd["lines"]}  # an unticked add-on is dropped, not re-suggested
    assert {l["sku"] for l in rd["lines"] if l["source"] == "add_on"} == {"PRO-START", "TIGER-PAW", "WEATHERWATCH", "SEA-RIDGE-CHAR"}
    assert rb["order_session_id"] and rb["order_session_id"] != body["order_session_id"]

    confirm = client.post("/api/order/confirm", json={"order_session_id": rb["order_session_id"], "duplicate_acknowledged": False})
    assert confirm.status_code == 200
    cb = confirm.json()
    assert cb["status"] == "confirmed" and cb["erp_submission"] == "simulated"
    record = cb["confirmation"]
    assert record["order_total"] == rd["pricing"]["total"] and record["sales_rep_id"] == "REP-001"
    assert record["commission_amount"] == rd["pricing"]["commission"]["amount"]
    assert [l["sku"] for l in record["lines"]] == [l["sku"] for l in rd["lines"] if l["included"]]
    assert record["delivery_date"] == rd["delivery_date_resolved"] and record["delivery_method"] == "job site"
    assert confirmed_orders_store.count_confirmed_orders() == 1
    assert client.get("/api/orders/confirmed", params={"rep_id": "REP-001"}).json()["confirmed_orders"][0]["order_session_id"] == rb["order_session_id"]
    assert client.get("/api/reps/REP-001/dashboard").json()["commission"]["session_sales_usd"] == rd["pricing"]["total"]

    again = client.post("/api/order/confirm", json={"order_session_id": rb["order_session_id"]})
    assert again.json()["status"] == "error" and confirmed_orders_store.count_confirmed_orders() == 1


def test_order_chat_needs_clarification_and_recheck_missing_field(monkeypatch):
    _mock_llm(monkeypatch, order_fields={"customerNameOrAlias": None, "items": []})
    resp = client.post("/api/order/chat", json={"message": "hiii"})
    body = resp.json()
    assert body["status"] == "needs_clarification" and body["order_session_id"] is None and body["order_details"] is None
    assert body["clarification"]["type"] == "missing_fields"

    recheck = client.post("/api/order/recheck", json={"customer_id": "ACC-1001", "product": "Timberline HDZ", "quantity": None, "unit": None})
    assert recheck.json()["status"] == "needs_clarification"


def test_blocked_order_has_no_session_and_cannot_be_confirmed(monkeypatch):
    _mock_llm(monkeypatch, order_fields={**ORDER_FIELDS, "customerNameOrAlias": "ACC-1004"})
    body = client.post("/api/order/chat", json={"message": "order"}).json()
    assert body["status"] == "blocked" and body["order_session_id"] is None
    assert client.post("/api/order/confirm", json={"order_session_id": "not-a-session"}).json()["status"] == "error"


# ---------------------------------------------------- assistant + friends

def test_assistant_chat_routes_and_serialises_the_location_alias(monkeypatch):
    _mock_llm(monkeypatch, route="CONTRACTOR")
    resp = client.post("/api/assistant/chat", json={"message": "roofers for Queen City Builders", "location": "Charlotte"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["routed_to"] == "contractor" and body["status"] == "answered"
    assert body["location"]["zip"] == "28202" and body["contractors"]
    assert body["agent_timeline"][0] == "Coordinator routed this to the Contractor Finder"

    _mock_llm(monkeypatch, route="ORDER")
    order = client.post("/api/assistant/chat", json={"message": "12 squares HDZ Charcoal for Sunshine"}).json()
    assert order["routed_to"] == "order" and order["order_session_id"] and order["order_details"]["sku"] == "TL-HDZ-01"

    hello = client.post("/api/assistant/chat", json={"message": "Hello"}).json()
    assert hello["routed_to"] == "chat" and hello["answer"].startswith("Hi!")


def test_warranty_chat_endpoint_answers_and_queues_reviews(monkeypatch):
    _mock_llm(monkeypatch, classification={"category": "ANSWERABLE", "product": "Timberline HDZ", "reason": "", "confidence": 0.95})
    answered = client.post("/api/warranty/chat", json={"question": "What do I need on a Timberline HDZ order for the WindProven warranty, and is HDZ approved for Florida?", "location": "Naples"}).json()
    assert answered["status"] == "answered" and answered["confidence"] >= 95 and answered["review"]["required"] is False
    assert {s["document_id"] for s in answered["sources"]} >= {"DOC-101", "DOC-102"}

    low = client.post("/api/warranty/chat", json={"question": "Is HDZ okay for coastal Florida if we mix in another manufacturer's ridge cap?"}).json()
    assert low["status"] == "needs_review" and low["review"]["review_id"].startswith("RV-")
    assert [r["review_id"] for r in client.get("/api/reviews").json()["reviews"]] == [low["review"]["review_id"]]

    urgent = client.post("/api/warranty/chat", json={"question": "The roof is leaking after last night and the ceiling is wet."}).json()
    assert urgent["status"] == "urgent_escalation" and urgent["escalation"]["urgent"] is True


def test_draft_email_and_email_intake(monkeypatch):
    _mock_llm(monkeypatch, synthesis="Subject: Your order\n\nDear Marcus,\n\nBest regards,\nJordan Reyes")
    draft = client.post("/api/assistant/draft-email", json={"history": [{"role": "user", "text": "12 squares please"}], "rep_id": "REP-001"})
    assert draft.status_code == 200 and draft.json()["recap"].startswith("Subject:")
    assert client.post("/api/assistant/draft-email", json={"history": []}).json()["recap"].startswith("Nothing to draft yet")

    _mock_llm(monkeypatch, route="WARRANTY")
    intake = client.post("/api/email/intake", json={"email_ids": ["EML-005", "EML-404"]})
    assert intake.status_code == 200
    items = intake.json()["items"]
    assert items[0]["status"] == "processed" and items[0]["result"]["routed_to"] == "warranty"
    assert items[0]["result"]["agent_timeline"][0].startswith("Email Agent extracted the request from Renee Ortiz's email (EML-005)")
    assert items[1]["status"] == "not_found"
    assert client.post("/api/email/intake", json={"email_ids": []}).status_code == 422
