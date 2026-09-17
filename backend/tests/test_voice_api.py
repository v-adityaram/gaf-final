"""/api/voice/* -- session minting is mocked; the tool endpoint is the voice
channel's bridge to the same Coordinator and confirm flow the text UI uses."""

from fastapi.testclient import TestClient

from app.api import voice as voice_module
from app.main import app
from app.services import order_service
from app.services.gaf_realtime import RealtimeSessionResult

client = TestClient(app)


def test_voice_session_returns_the_client_secret_and_optional_turn(monkeypatch):
    async def fake_create_realtime_session():
        return RealtimeSessionResult(success=True, client_secret="tok-123", realtime_url="https://example/realtime/calls")

    monkeypatch.setattr(voice_module, "create_realtime_session", fake_create_realtime_session)
    monkeypatch.setattr(voice_module, "generate_turn_credentials", lambda: None)
    body = client.post("/api/voice/session").json()
    assert body["success"] is True and body["client_secret"] == "tok-123" and body["turn"] is None

    monkeypatch.setattr(voice_module, "generate_turn_credentials", lambda: {"urls": ["turns:turn.example.com:5349?transport=tcp"], "username": "1", "credential": "abc"})
    assert client.post("/api/voice/session").json()["turn"]["urls"] == ["turns:turn.example.com:5349?transport=tcp"]


def test_voice_session_surfaces_failure(monkeypatch):
    async def fake_create_realtime_session():
        return RealtimeSessionResult(success=False, error="realtime_session_timeout")

    monkeypatch.setattr(voice_module, "create_realtime_session", fake_create_realtime_session)
    body = client.post("/api/voice/session").json()
    assert body["success"] is False and body["error"] == "realtime_session_timeout"


def test_voice_tool_forwards_customer_requests_to_the_coordinator(monkeypatch):
    seen = {}

    async def fake_run_assistant_chat(message, location=None):
        seen["args"] = (message, location)
        return {"routed_to": "order", "status": "ready_for_review", "order_session_id": "sess-1", "agent_timeline": []}

    monkeypatch.setattr(voice_module.assistant_orchestrator, "run_assistant_chat", fake_run_assistant_chat)
    body = client.post("/api/voice/tool", json={"function_name": "handle_customer_request", "message": "12 squares Timberline HDZ Charcoal", "location": "Tampa"}).json()
    assert body["success"] is True and body["data"]["order_session_id"] == "sess-1"
    assert seen["args"] == ("12 squares Timberline HDZ Charcoal", "Tampa")
    assert client.get("/api/metrics/requests").json()["requests"][0]["request_type"] == "Voice"
    assert client.post("/api/voice/tool", json={"function_name": "handle_customer_request"}).json() == {"success": False, "data": None, "error": "missing_message"}


def test_voice_tool_confirms_a_pending_order_with_duplicate_acknowledged():
    session_id = order_service.create_session({"status": "ready_for_review", "order_details": {"credit_check_status": "PASSED", "duplicate_check_status": "WARNING", "pricing": {}, "lines": []}})
    body = client.post("/api/voice/tool", json={"function_name": "confirm_pending_order", "order_session_id": session_id}).json()
    assert body["success"] is True and body["data"]["status"] == "confirmed"
    assert order_service.get_session(session_id)["duplicate_acknowledged"] is True
    assert client.post("/api/voice/tool", json={"function_name": "confirm_pending_order"}).json()["error"] == "missing_order_session_id"
    assert client.post("/api/voice/tool", json={"function_name": "delete_everything"}).json()["error"] == "unknown_function"
