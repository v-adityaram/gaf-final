"""Contractor Finder against the real ZIP/contractor directory. Deterministic
paths (ZIP or city in the message, customer's own city) never call the
model; only a location-less message triggers the small extraction call."""

import asyncio

from app import foundry_client
from app.orchestrators import contractor_orchestrator


def _no_llm(monkeypatch):
    def fail(prompt):
        raise AssertionError("deterministic path must not call the model")

    monkeypatch.setattr(foundry_client, "call_model_json", fail)


def _search(message, location=None):
    return asyncio.run(contractor_orchestrator.run_contractor_search(message, location))


def test_zip_in_message_returns_contractors_sorted_by_distance(monkeypatch):
    _no_llm(monkeypatch)
    result = _search("Find GAF-certified roofers near 30061")
    assert result["status"] == "answered"
    assert result["location"]["city"] == "Marietta" and result["location"]["state"] == "GA"
    dists = [c["distanceMiles"] for c in result["contractors"]]
    assert dists == sorted(dists) and 0 < len(dists) <= 8
    assert result["sources"] == [{"document_id": "DOC-111", "title": "Contractor Certification Tiers", "version": "Web-2026-09-15"}]
    assert result["answer"].startswith(f"{len(dists)} GAF-certified contractors near Marietta, GA 30061")
    assert result["provider"] is None and result["model"] is None


def test_master_elite_wording_raises_the_minimum_tier(monkeypatch):
    _no_llm(monkeypatch)
    result = _search("Find GAF-certified roofers near 30061, ideally Master Elite.")
    assert result["contractors"]
    assert all(c["certificationTier"] in ("master_elite", "presidents_club") for c in result["contractors"])
    assert "(Master Elite or higher)" in result["answer"]


def test_customer_name_resolves_to_the_customers_own_city(monkeypatch):
    _no_llm(monkeypatch)
    result = _search("Which certified contractors could install a UHDZ roof for Queen City Builders' homeowner in Charlotte?")
    assert result["status"] == "answered"
    assert result["location"]["zip"] == "28202" and result["location"]["city"] == "Charlotte"
    assert result["contractors"]


def test_customer_alias_alone_uses_the_account_zip(monkeypatch):
    _no_llm(monkeypatch)
    result = _search("Need a couple of installers for Queen City Builders")
    assert result["status"] == "answered"
    assert result["location"]["zip"] == "28202"
    assert "Used Charlotte Home Builder Group 11's account ZIP 28202" in result["agent_timeline"][1]


def test_unknown_zip_is_no_source(monkeypatch):
    _no_llm(monkeypatch)
    result = _search("Contractors near 99999")
    assert result["status"] == "no_source"
    assert result["contractors"] == [] and result["location"] is None
    assert "ZIP '99999' is not in the prototype directory" in result["answer"]


def test_no_location_falls_back_to_the_model_then_asks(monkeypatch):
    calls = []

    def extract(prompt):
        calls.append(prompt)
        assert "Read this request for roofing contractors" in prompt
        return {"zip": None, "city": None, "customerNameOrAlias": None, "minTier": None}

    monkeypatch.setattr(foundry_client, "call_model_json", extract)
    result = _search("Find me some good roofers please")
    assert result["status"] == "needs_clarification"
    assert result["clarification"]["type"] == "location_needed" and result["clarification"]["quick_replies"]
    assert result["provider"] == "foundry"
    assert len(calls) == 1

    monkeypatch.setattr(foundry_client, "call_model_json", lambda prompt: {"zip": "28202", "city": None, "customerNameOrAlias": None, "minTier": "certified_plus"})
    resolved = _search("Find me some good roofers please")
    assert resolved["status"] == "answered" and resolved["location"]["city"] == "Charlotte"
    assert all(c["certificationTier"] != "certified" for c in resolved["contractors"])
