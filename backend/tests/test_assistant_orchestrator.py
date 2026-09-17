"""The Coordinator: one mocked routing call decides ORDER / WARRANTY /
CONTRACTOR / GENERAL / CHAT, then the chosen specialist is called unchanged
(mocked here so the routing decision itself is what's asserted), plus the
deterministic overrides that never depend on the model."""

import asyncio

import pytest

from app import foundry_client
from app.orchestrators import assistant_orchestrator, contractor_orchestrator, general_query_orchestrator, order_orchestrator, warranty_orchestrator

SPECIALISTS = {
    "order": (order_orchestrator, "run_order_chat"),
    "warranty": (warranty_orchestrator, "run_warranty_chat"),
    "contractor": (contractor_orchestrator, "run_contractor_search"),
    "general": (general_query_orchestrator, "run_general_query_chat"),
}


def _stub_specialists(monkeypatch, seen):
    """Every specialist records that it was called; none does real work."""
    for name, (module, fn) in SPECIALISTS.items():
        async def fake(message, *args, _name=name, **kwargs):
            seen[_name] = (message, args, kwargs)
            return {"status": "answered", "answer": f"{_name} answer", "sources": [], "agent_timeline": [f"{_name} step"]}

        monkeypatch.setattr(module, fn, fake)


def _route(monkeypatch, route, **extra):
    def classify(prompt):
        assert "Decide which specialist" in prompt
        return {"route": route, "tone": "neutral", "chat_intent": None, **extra}

    monkeypatch.setattr(foundry_client, "call_model_json", classify)


@pytest.mark.parametrize("route,expected,label", [
    ("ORDER", "order", "Smart Order Agent"),
    ("WARRANTY", "warranty", "Product & Warranty Agent"),
    ("CONTRACTOR", "contractor", "Contractor Finder"),
    ("GENERAL", "general", "General Inquiry Handler"),
    ("SOMETHING_ELSE", "warranty", "Product & Warranty Agent"),
])
def test_route_dispatches_to_exactly_one_specialist(monkeypatch, route, expected, label):
    seen = {}
    _stub_specialists(monkeypatch, seen)
    _route(monkeypatch, route)
    history = [{"role": "user", "text": "earlier"}]

    result = asyncio.run(assistant_orchestrator.run_assistant_chat("Some business question about a roof", "Tampa", history))

    assert list(seen) == [expected]
    assert result["routed_to"] == expected
    assert result["answer"] == f"{expected} answer"
    assert result["agent_timeline"][0] == f"Coordinator routed this to the {label}"
    assert result["agent_timeline"][1] == f"{expected} step"
    assert result["tone"] == "neutral" and result["handoff_suggested"] is False
    message, args, kwargs = seen[expected]
    assert message == "Some business question about a roof"
    assert history in args  # conversation memory is forwarded


def test_chat_replies_never_run_a_business_workflow(monkeypatch):
    seen = {}
    _stub_specialists(monkeypatch, seen)
    cases = [
        ("thanks", "Thank you", "You're welcome!"),
        ("help", "What can you do?", "I can: build and price an order"),
        ("goodbye", "Bye", "come back whenever"),
        ("unrelated", "Write a recipe", "I can help with roofing orders"),
        (None, "???", "I can: build and price an order"),  # unknown intent falls back to help
    ]
    for intent, message, expected in cases:
        _route(monkeypatch, "CHAT", chat_intent=intent)
        result = asyncio.run(assistant_orchestrator.run_assistant_chat(message))
        assert seen == {}
        assert result["routed_to"] == "chat" and result["status"] == "answered"
        assert expected in result["answer"], intent
        assert result["agent_timeline"] == ["Coordinator handled the conversation"]
        assert "order_session_id" not in result


def test_standalone_greeting_skips_the_model_entirely(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("greeting must not call the model or a specialist")

    monkeypatch.setattr(foundry_client, "call_model_json", fail)
    _stub_specialists(monkeypatch, {})
    for message in ["Hello", "Hii", "HI!", "  Hello  ", "Hey there!", "Good morning"]:
        result = asyncio.run(assistant_orchestrator.run_assistant_chat(message))
        assert result["routed_to"] == "chat", message
        assert result["answer"].startswith("Hi! I can prepare and price a roofing order")


def test_greeting_followed_by_business_still_goes_to_the_classifier(monkeypatch):
    seen = {}
    _stub_specialists(monkeypatch, seen)
    prompts = {}

    def classify(prompt):
        prompts["p"] = prompt
        return {"route": "ORDER", "tone": "neutral"}

    monkeypatch.setattr(foundry_client, "call_model_json", classify)
    result = asyncio.run(assistant_orchestrator.run_assistant_chat("Hello, I need 12 squares of Timberline HDZ"))
    assert result["routed_to"] == "order"
    assert "Hello, I need 12 squares" in prompts["p"]


def test_order_number_lookup_overrides_the_model_to_general(monkeypatch):
    seen = {}
    _stub_specialists(monkeypatch, seen)
    _route(monkeypatch, "ORDER")
    result = asyncio.run(assistant_orchestrator.run_assistant_chat("Show me ORD-77012"))
    assert list(seen) == ["general"]
    assert result["routed_to"] == "general"
    assert result["agent_timeline"][0] == "Coordinator routed this to the General Inquiry Handler (deterministic override: order-number lookup)"

    # A reorder "same as ORD-..." is a new order, not a lookup.
    seen.clear()
    result = asyncio.run(assistant_orchestrator.run_assistant_chat("Reorder 60 squares same as ORD-77009, show me the total"))
    assert list(seen) == ["order"]


def test_contractor_wording_with_a_zip_overrides_the_model(monkeypatch):
    seen = {}
    _stub_specialists(monkeypatch, seen)
    _route(monkeypatch, "WARRANTY")
    result = asyncio.run(assistant_orchestrator.run_assistant_chat("Find GAF-certified roofers near 30061"))
    assert list(seen) == ["contractor"]
    assert result["routed_to"] == "contractor"
    assert "deterministic override: contractor wording with a location" in result["agent_timeline"][0]


def test_handoff_is_suggested_for_explicit_asks_or_frustration(monkeypatch):
    seen = {}
    _stub_specialists(monkeypatch, seen)
    for message, tone, expected_handoff in [
        ("Can I speak to a manager please", "neutral", True),
        ("Connect me with a real person", "neutral", True),
        ("This is the third time I'm asking!!", "frustrated", True),
        ("What warranty does Timberline HDZ carry?", "neutral", False),
    ]:
        _route(monkeypatch, "WARRANTY", tone=tone)
        result = asyncio.run(assistant_orchestrator.run_assistant_chat(message))
        assert result["tone"] == tone, message
        assert result["handoff_suggested"] is expected_handoff, message
        if expected_handoff:
            assert result["agent_timeline"][1] == "Coordinator flagged this conversation for a human handoff offer"


def test_chat_handoff_reply_never_claims_a_transfer_happened(monkeypatch):
    _route(monkeypatch, "CHAT", chat_intent="greeting")
    result = asyncio.run(assistant_orchestrator.run_assistant_chat("Transfer me to a human"))
    assert result["handoff_suggested"] is True
    assert result["answer"].startswith("Understood -- I'll flag this for a human.")
