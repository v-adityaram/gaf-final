"""General Inquiry Handler: mocked extraction + synthesis, real record
fetches from the local dataset."""

import asyncio

from app import foundry_client
from app.orchestrators import general_query_orchestrator


def _mock(monkeypatch, extraction, answer="Grounded answer."):
    seen = {}

    def call_model_json(prompt):
        assert "Identify what this roofing-supply question" in prompt
        return extraction

    def call_model(prompt):
        seen["synthesis"] = prompt
        return answer

    monkeypatch.setattr(foundry_client, "call_model_json", call_model_json)
    monkeypatch.setattr(foundry_client, "call_model", call_model)
    return seen


def _ask(message):
    return asyncio.run(general_query_orchestrator.run_general_query_chat(message))


def test_order_id_lookup_returns_the_order_and_its_customer(monkeypatch):
    seen = _mock(monkeypatch, {"customerNameOrAlias": None, "productDescriptions": [], "orderId": "ORD-77012"})
    result = _ask("Show me ORD-77012")
    assert result["status"] == "answered"
    assert result["order"]["orderId"] == "ORD-77012" and result["order"]["accountId"] == "ACC-1012" and result["order"]["status"] == "Allocated"
    assert '"accountId": "ACC-1012"' in seen["synthesis"] and '"tradeName": "Garden State Supply"' in seen["synthesis"]
    assert result["products"] == [] and result["provider"] == "foundry"


def test_order_id_in_the_text_is_used_even_when_extraction_misses_it(monkeypatch):
    _mock(monkeypatch, {"customerNameOrAlias": None, "productDescriptions": [], "orderId": None})
    result = _ask("what happened to ord-77009?")
    assert result["order"]["orderId"] == "ORD-77009"


def test_product_comparison_returns_one_card_per_family_first_and_fetches_prices(monkeypatch):
    seen = _mock(monkeypatch, {"customerNameOrAlias": None, "productDescriptions": ["Timberline HDZ", "Timberline UHDZ"], "orderId": None})
    result = _ask("What's the difference between Timberline HDZ and UHDZ, and what does each cost per square?")
    assert result["status"] == "answered"
    assert [c["product_family"] for c in result["products"][:2]] == ["Timberline HDZ", "Timberline UHDZ"]
    assert len(result["products"]) == 6
    assert result["products"][0]["price_per_square"] == 118.5 and result["products"][1]["price_per_square"] == 156.0
    assert '"activeDiscounts"' in seen["synthesis"] and '"passages"' in seen["synthesis"] and '"inventory"' in seen["synthesis"]
    assert result["sources"] and all(s["title"] == "Knowledge passage" for s in result["sources"])


def test_customer_credit_question_and_unresolvable_targets(monkeypatch):
    seen = _mock(monkeypatch, {"customerNameOrAlias": "Sunshine Roofing Supply", "productDescriptions": [], "orderId": None})
    result = _ask("What is Sunshine Roofing Supply's credit situation?")
    assert result["status"] == "answered"
    assert '"availableCredit": 65000.0' in seen["synthesis"] and '"recentOrders"' in seen["synthesis"]

    _mock(monkeypatch, {"customerNameOrAlias": "Tampa Contractor", "productDescriptions": [], "orderId": None})
    ambiguous = _ask("credit for Tampa Contractor?")
    assert ambiguous["status"] == "needs_clarification" and "more than one account matches" in ambiguous["answer"]

    _mock(monkeypatch, {"customerNameOrAlias": None, "productDescriptions": [], "orderId": None})
    nothing = _ask("tell me something")
    assert nothing["status"] == "needs_clarification" and nothing["answer"] == "Which customer, order or product is this question about?"

    _mock(monkeypatch, {"customerNameOrAlias": None, "productDescriptions": ["Camelot II"], "orderId": None}, answer="NO_SOURCE")
    withheld = _ask("Camelot II lead time?")
    assert withheld["status"] == "no_source" and withheld["products"][0]["sku"] == "CAM-II-01"
