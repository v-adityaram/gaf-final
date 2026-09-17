"""Conversation memory, the email intake agent, the customer-email drafter,
roof-photo intake and feedback capture. All offline: every model call is
mocked (dispatching on prompt text where more than one call happens) and
every assertion is about what THIS code does with the model's output."""

import asyncio

from fastapi.testclient import TestClient

from app import foundry_client
from app.main import app
from app.orchestrators import assistant_orchestrator, email_orchestrator, order_orchestrator, photo_orchestrator, recap_orchestrator, warranty_orchestrator
from app.orchestrators.history import format_history
from app.services import feedback_service

client = TestClient(app)

HISTORY = [
    {"role": "user", "text": "I need 12 squares of Timberline HDZ Charcoal for Sunshine Roofing"},
    {"role": "assistant", "text": "Customer: Tampa Contractor Group 01 (ACC-1001)\nSKU: TL-HDZ-01\nFinal Status: READY FOR HUMAN REVIEW"},
]


# ---- history formatting

def test_format_history_renders_oldest_first_flattens_and_truncates():
    text = format_history(HISTORY)
    assert text.startswith("Earlier in this conversation")
    assert text.index("Customer: I need 12 squares") < text.index("Assistant: Customer: Tampa")
    assert "\n" not in text.split("Assistant: ")[1]
    assert format_history(None) == "" and format_history([{"role": "user", "text": ""}]) == ""
    many = format_history([{"role": "user", "text": f"turn {i}"} for i in range(20)])
    assert "turn 0" not in many and "turn 19" in many


def test_history_reaches_the_order_and_warranty_prompts(monkeypatch):
    captured = []

    def fake(prompt):
        captured.append(prompt)
        if "Extract fields" in prompt:
            return {"customerNameOrAlias": None, "items": []}
        return {"category": "ANSWERABLE", "product": None, "reason": "", "confidence": 0.5}

    monkeypatch.setattr(foundry_client, "call_model_json", fake)
    asyncio.run(order_orchestrator.run_order_chat("make it 80 squares", HISTORY))
    asyncio.run(warranty_orchestrator.run_warranty_chat("and near Naples?", "Naples", HISTORY))
    assert all("I need 12 squares of Timberline HDZ Charcoal" in p for p in captured)
    assert "(with conversation context)" in asyncio.run(order_orchestrator.run_order_chat("x", HISTORY))["agent_timeline"][0]


# ---- email intake

def test_email_intake_extracts_the_request_then_runs_the_coordinator(monkeypatch):
    prompts = []

    def call_model_json(prompt):
        prompts.append(prompt)
        if "A customer emailed" in prompt:
            assert "Sunshine Roofing Supply (ACC-1001)" in prompt and "42 squares of Timberline HDZ in Charcoal" in prompt
            return {"intent": "order", "request": "Sunshine Roofing Supply (ACC-1001): 42 squares Timberline HDZ Charcoal with starter, underlayment and ridge cap, deliver Tampa next Wednesday.", "summary": "42 sq HDZ Charcoal + add-ons, Tampa"}
        if "Decide which specialist" in prompt:
            return {"route": "ORDER", "tone": "neutral", "chat_intent": None}
        assert "Extract fields" in prompt
        return {"customerNameOrAlias": "ACC-1001", "items": [{"productDescription": "Timberline HDZ", "colour": "Charcoal", "quantity": 42, "unit": "squares"}],
                "includeAddOns": None, "deliveryCity": "Tampa", "deliveryDate": "next Wednesday", "deliveryMethod": None, "referenceOrderId": None, "quoteReference": False, "roofEstimate": None}

    monkeypatch.setattr(foundry_client, "call_model_json", call_model_json)
    result = asyncio.run(email_orchestrator.run_email_intake(["EML-001", "EML-999"]))

    assert len(prompts) == 3
    processed, missing = result["items"]
    assert processed["status"] == "processed" and processed["intent"] == "order"
    assert processed["email"]["fromName"] == "Marcus Bell" and processed["email"]["accountId"] == "ACC-1001"
    inner = processed["result"]
    assert inner["routed_to"] == "order" and inner["status"] == "ready_for_review"
    assert inner["order_details"]["total_squares"] == 42
    assert {l["sku"] for l in inner["order_details"]["lines"] if l["included"]} >= {"TL-HDZ-01", "PRO-START", "TIGER-PAW", "SEA-RIDGE-CHAR"}
    assert inner["agent_timeline"][0] == "Email Agent extracted the request from Marcus Bell's email (EML-001)"
    assert missing == {"email_id": "EML-999", "status": "not_found", "request": None, "result": None}
    assert result["provider"] == "foundry"


def test_email_intake_falls_back_to_the_raw_email_when_extraction_is_empty(monkeypatch):
    seen = {}

    def call_model_json(prompt):
        if "A customer emailed" in prompt:
            return {}
        return {"route": "CHAT", "tone": "neutral", "chat_intent": "help"}

    monkeypatch.setattr(foundry_client, "call_model_json", call_model_json)

    async def fake_coordinator(request, location=None, history=None):
        seen["request"] = request
        return {"routed_to": "chat", "status": "answered", "answer": "ok", "agent_timeline": []}

    monkeypatch.setattr(assistant_orchestrator, "run_assistant_chat", fake_coordinator)
    asyncio.run(email_orchestrator.run_email_intake(["EML-005"]))
    assert seen["request"].startswith("Naples Home Builder Group 02 (ACC-1002) emailed: WindProven question before we quote.")


# ---- customer email draft

def test_recap_formats_the_rep_and_uses_only_the_transcript(monkeypatch):
    captured = {}

    def fake_call(prompt):
        assert "Draft a professional" in prompt
        captured["prompt"] = prompt
        return "Subject: Your Timberline HDZ order\n\nDear Marcus,\n\nNext steps: confirm\n\nBest regards,\nJordan Reyes"

    monkeypatch.setattr(foundry_client, "call_model", fake_call)
    result = recap_orchestrator.run_recap(HISTORY, {"name": "Jordan Reyes", "title": "Territory Sales Manager", "phone": "(813) 555-0142"})
    assert "I need 12 squares" in captured["prompt"]
    assert "Jordan Reyes\nTerritory Sales Manager\n(813) 555-0142" in captured["prompt"]
    assert result["recap"].startswith("Subject:")
    assert result["agent_timeline"] == ["Email Writer drafted a customer email from the transcript only"]

    recap_orchestrator.run_recap(HISTORY, None)
    assert "GAF Sales Representative\nTerritory Sales" in captured["prompt"]


def test_recap_with_empty_history_never_calls_the_model(monkeypatch):
    def fail(prompt):
        raise AssertionError("model should not be called with nothing to draft")

    monkeypatch.setattr(foundry_client, "call_model", fail)
    result = recap_orchestrator.run_recap([])
    assert result["recap"].startswith("Nothing to draft yet")
    assert result["agent_timeline"] == ["No conversation to draft from"]


# ---- photo intake

DATA_URL = "data:image/jpeg;base64," + "A" * 64


def test_photo_not_roofing_never_asks_the_advisor(monkeypatch):
    monkeypatch.setattr(foundry_client, "call_model_vision_json", lambda prompt, url: {"isRoofingRelated": False, "whatIsVisible": "a cat"})

    def fail(*args, **kwargs):
        raise AssertionError("warranty advisor must not be called for a non-roof image")

    monkeypatch.setattr(warranty_orchestrator, "run_warranty_chat", fail)
    result = asyncio.run(photo_orchestrator.run_photo_intake(DATA_URL, None, "Tampa"))
    assert result["status"] == "not_a_roof" and result["warranty"] is None and result["question"] is None


def test_photo_urgent_signs_and_product_guess_shape_the_advisor_question(monkeypatch):
    monkeypatch.setattr(foundry_client, "call_model_vision_json", lambda prompt, url: {
        "isRoofingRelated": True, "whatIsVisible": "water stain under shingles", "possibleIssues": ["stain"], "urgentSigns": True,
        "productGuess": "Timberline HDZ", "questionForAdvisor": "What should be done about water staining?"})
    seen = {}

    async def fake_warranty(question, location=None, history=None):
        seen["question"] = question
        return {"status": "urgent_escalation", "answer": "URGENT ESCALATION", "sources": [], "agent_timeline": ["esc"]}

    monkeypatch.setattr(warranty_orchestrator, "run_warranty_chat", fake_warranty)
    result = asyncio.run(photo_orchestrator.run_photo_intake(DATA_URL, "customer says it drips", "Tampa"))
    assert result["status"] == "analyzed"
    assert seen["question"] == "Possible leak or product defect seen in a customer photo. For Timberline HDZ: What should be done about water staining?"
    assert warranty_orchestrator._URGENT_PATTERN.search(seen["question"])  # the real regex fires on this question
    assert "esc" in result["agent_timeline"] and "Urgent signs flagged in the photo -- routing as urgent" in result["agent_timeline"]


def test_photo_endpoint_rejects_non_image_payload():
    assert client.post("/api/assistant/photo", json={"image_data_url": "data:text/plain;base64," + "A" * 64}).status_code == 400


# ---- feedback

def test_feedback_is_recorded_and_summarized(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback_service, "FEEDBACK_FILE", tmp_path / "feedback.jsonl")
    feedback_service.reset_all()
    up = client.post("/api/feedback", json={"rating": "up", "route": "order", "status": "ready_for_review"})
    down = client.post("/api/feedback", json={"rating": "down", "route": "warranty", "comment": "wrong doc"})
    assert up.status_code == 200 and down.status_code == 200 and up.json()["feedback_id"]
    summary = client.get("/api/feedback/summary").json()
    assert (summary["up"], summary["down"], summary["total"]) == (1, 1, 2)
    assert summary["recent"][0]["comment"] == "wrong doc"
    assert (tmp_path / "feedback.jsonl").read_text().count("\n") == 2
    assert client.post("/api/feedback", json={"rating": "meh"}).status_code == 400
    feedback_service.reset_all()
