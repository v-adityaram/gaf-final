"""Scenario tests driven by data/demo_scenarios/use_cases.json -- the demo
menu's own order and advisor scenarios run through the real orchestrators
against the real local dataset, with only the LLM calls mocked. Each test
asserts the scenario's documented expectation."""

import asyncio

import pytest

from app import foundry_client
from app.orchestrators import order_orchestrator, warranty_orchestrator
from app.services import local_data_repository as repo

USE_CASES = repo.catalog.use_cases()
ORDER_SCENARIOS = {s["scenario_id"]: s for s in USE_CASES["orderScenarios"]}
ADVISOR_SCENARIOS = {s["scenario_id"]: s for s in USE_CASES["advisorScenarios"]}
UC = {u["id"]: u for u in USE_CASES["useCases"]}


def _extraction_for(scenario, **overrides):
    """What the extraction call would return for an order scenario's
    utterance ("Need 12 squares of Timberline HDZ Shingles in Charcoal for
    Tampa Contractor Group 01, deliver to Tampa...")."""
    fields = {
        "customerNameOrAlias": scenario["account_id"],
        "items": [{"productDescription": " ".join(scenario["utterance"].split(" of ")[1].split(" in ")[0].split()[:2]), "colour": scenario["utterance"].split(" in ")[1].split(" for ")[0],
                   "quantity": scenario["quantity"], "unit": scenario["unit"]}],
        "includeAddOns": None, "deliveryCity": scenario["ship_to_city"], "deliveryDate": scenario["requested_date"], "deliveryMethod": "job site",
        "referenceOrderId": None, "quoteReference": False, "roofEstimate": None,
    }
    fields.update(overrides)
    return fields


def _run_order(monkeypatch, fields, message):
    monkeypatch.setattr(foundry_client, "call_model_json", lambda prompt: fields)
    return asyncio.run(order_orchestrator.run_order_chat(message))


def _run_warranty(monkeypatch, question, classification, synthesis="Answer from evidence.\nSource: x"):
    monkeypatch.setattr(foundry_client, "call_model_json", lambda prompt: classification)
    monkeypatch.setattr(foundry_client, "call_model", lambda prompt: synthesis)
    return asyncio.run(warranty_orchestrator.run_warranty_chat(question))


@pytest.mark.parametrize("scenario_id", ["OS-001", "OS-019"])
def test_happy_path_scenarios_prepare_the_expected_sku_and_wait_for_a_human(monkeypatch, scenario_id):
    s = ORDER_SCENARIOS[scenario_id]
    result = _run_order(monkeypatch, _extraction_for(s), s["utterance"])
    assert result["status"] == "ready_for_review"
    d = result["order_details"]
    assert d["customer_id"] == s["account_id"] and d["sku"] == s["expected_sku"]
    assert d["quantity"] == s["quantity"] and d["converted_quantity"] == s["quantity"] * 3
    assert d["credit_check_status"] == "PASSED" and d["duplicate_check_status"] == "PASSED"
    assert d["delivery_date_resolved"] == s["requested_date"]
    assert result["order_session_id"]  # prepared, still needs the human click
    assert {g["key"]: g["status"] for g in result["guardrails"]}["human_confirmation_required"] == "PASSED"


@pytest.mark.parametrize("scenario_id", ["OS-004", "OS-022"])
def test_credit_hold_scenarios_block_and_never_promise_delivery(monkeypatch, scenario_id):
    s = ORDER_SCENARIOS[scenario_id]
    result = _run_order(monkeypatch, _extraction_for(s, deliveryDate="tomorrow"), s["utterance"])
    assert result["status"] == "blocked"
    assert result["order_details"]["credit_check_status"] == "BLOCKED"
    assert "order_session_id" not in result
    assert "do not promise a delivery date" in " ".join(result["order_details"]["warnings"])


def test_uc08_ambiguous_alias_asks_which_account(monkeypatch):
    fields = {"customerNameOrAlias": "Tampa Contractor", "items": [{"productDescription": "HDZ", "colour": "Charcoal", "quantity": 20, "unit": "squares"}]}
    result = _run_order(monkeypatch, fields, UC["UC-08"]["prompt"])
    assert result["status"] == "needs_clarification"
    assert result["clarification"]["type"] == "customer_ambiguous"
    assert set(result["clarification"]["quick_replies"]) == {"Use ACC-1001", "Use ACC-1013"}


def test_uc06_reorder_flags_the_referenced_order_as_a_duplicate(monkeypatch):
    fields = {"customerNameOrAlias": "Lone Star Distribution", "items": [{"productDescription": "Timberline UHDZ", "colour": "Charcoal", "quantity": 60, "unit": "squares"}],
              "deliveryCity": "Dallas", "referenceOrderId": "ORD-77009"}
    result = _run_order(monkeypatch, fields, UC["UC-06"]["prompt"])
    assert result["order_details"]["duplicate_check_status"] == "WARNING"
    assert "ORD-77009" in " ".join(result["order_details"]["warnings"])


def test_os017_quote_reference_is_a_pricing_exception(monkeypatch):
    s = ORDER_SCENARIOS["OS-017"]
    result = _run_order(monkeypatch, _extraction_for(s, quoteReference=True), s["utterance"] + " Honour the July quote.")
    assert result["status"] == "ready_for_review"
    assert any("pricing exception" in w and "DOC-110" in w for w in result["order_details"]["warnings"])


def test_os018_missing_requested_date_is_asked_for(monkeypatch):
    s = ORDER_SCENARIOS["OS-018"]
    result = _run_order(monkeypatch, _extraction_for(s, deliveryDate=None), s["utterance"])
    assert result["order_details"]["delivery_date"] is None
    assert "No requested delivery date" in " ".join(result["order_details"]["warnings"])


@pytest.mark.parametrize("scenario_id,expected_status", [("AS-004", "escalated"), ("AS-005", "urgent_escalation"), ("AS-014", "escalated")])
def test_advisor_escalation_scenarios(monkeypatch, scenario_id, expected_status):
    s = ADVISOR_SCENARIOS[scenario_id]
    assert s["escalation_expected"] is True
    result = _run_warranty(monkeypatch, s["question"], {"category": "ANSWERABLE", "product": None, "reason": "misread", "confidence": 0.9})
    assert result["status"] == expected_status
    assert result["escalation"]["destination"] == "Technical Services"


def test_advisor_no_source_and_expired_trap_scenarios(monkeypatch):
    def fail(prompt):
        raise AssertionError("no synthesis without evidence")

    monkeypatch.setattr(foundry_client, "call_model", fail)
    monkeypatch.setattr(foundry_client, "call_model_json", lambda prompt: {"category": "ANSWERABLE", "product": None, "reason": "", "confidence": 0.9})
    no_source = asyncio.run(warranty_orchestrator.run_warranty_chat(ADVISOR_SCENARIOS["AS-006"]["question"]))
    assert no_source["status"] == "no_source"

    seen = {}

    def synth(prompt):
        seen["prompt"] = prompt
        return "The prototype defines two tiers.\nSource: Prototype Wind Warranty Rules — vSynthetic-1"

    monkeypatch.setattr(foundry_client, "call_model", synth)
    trap = asyncio.run(warranty_orchestrator.run_warranty_chat(ADVISOR_SCENARIOS["AS-007"]["question"]))
    assert "DOC-OLD" not in seen["prompt"]
    assert all(src["document_id"] != "DOC-OLD" for src in trap["sources"])
    assert trap["status"] == "needs_review"  # steering the sources is itself a confidence penalty
