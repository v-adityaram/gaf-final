"""Secret/error guard: never let a raw exception message -- which could echo
request/response internals, API error bodies, or anything else
server-internal -- reach the client. Full detail is logged server-side only
(see main.py's _safe_detail / unhandled_exception_handler); the client
always gets a fixed, generic message."""

from fastapi.testclient import TestClient

from app import foundry_client
from app.foundry_client import FoundryCallError, FoundryNotConfiguredError
from app.main import app
from app.orchestrators import order_orchestrator

client = TestClient(app)

SECRET = "sk-live-totally-real-api-key-should-never-leak-9f8e7d6c"


def test_foundry_call_error_is_a_generic_502_that_never_leaks_its_message(monkeypatch):
    def boom(prompt):
        raise FoundryCallError(f"Azure AI Foundry call failed: Authorization header 'api-key: {SECRET}' rejected")

    monkeypatch.setattr(foundry_client, "call_model_json", boom)
    for path, payload in [
        ("/api/order/chat", {"message": "order"}),
        ("/api/assistant/chat", {"message": "What warranty does Timberline HDZ carry?"}),
        ("/api/warranty/chat", {"question": "What warranty does Timberline HDZ carry?"}),
        ("/api/email/intake", {"email_ids": ["EML-001"]}),
    ]:
        resp = client.post(path, json=payload)
        assert resp.status_code == 502, path
        assert SECRET not in resp.text
        assert resp.json() == {"detail": "The AI service is temporarily unavailable. Please try again."}


def test_foundry_not_configured_error_is_a_503_without_env_values(monkeypatch):
    def not_configured(prompt):
        raise FoundryNotConfiguredError("FOUNDRY_API_KEY=sk-should-not-appear must both be set")

    monkeypatch.setattr(foundry_client, "call_model_json", not_configured)
    resp = client.post("/api/order/chat", json={"message": "order"})
    assert resp.status_code == 503
    assert "sk-should-not-appear" not in resp.text
    assert resp.json()["detail"] == "The AI service is not configured. Please contact an administrator."


def test_unhandled_exception_never_leaks_a_stack_trace_or_message(monkeypatch):
    async def fake_run(message, history=None):
        raise RuntimeError(f"unexpected failure touching /etc/secrets/{SECRET}.pem")

    monkeypatch.setattr(order_orchestrator, "run_order_chat", fake_run)
    local_client = TestClient(app, raise_server_exceptions=False)
    resp = local_client.post("/api/order/chat", json={"message": "order"})
    assert resp.status_code == 500
    assert SECRET not in resp.text and "Traceback" not in resp.text and ".pem" not in resp.text
    assert resp.json()["detail"] == "Something went wrong. Please try again."
