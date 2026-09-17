"""The Coordinator: receives one rep message and decides which specialist
handles it -- Smart Order, Product & Warranty, Contractor Finder, or the
General Inquiry handler -- then calls that orchestrator unchanged.

Routing is a single fast classification call, decided fresh on every
turn (the demo switches topic mid-conversation). Deterministic overrides
win over the model: an order number pattern ("ORD-77012") with lookup
wording goes to General (never a new order), a ZIP + "contractor" goes to
Contractor Finder, and an explicit ask for a person sets handoff_suggested
regardless of tone.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app import foundry_client
from app.orchestrators import contractor_orchestrator, general_query_orchestrator, order_orchestrator, warranty_orchestrator
from app.orchestrators.history import format_history

_ROUTE_PROMPT = """Decide which specialist should handle the latest message from a roofing-supply sales rep, and \
read the customer's tone.

- "ORDER" -- placing, preparing, quoting or changing a roofing product order: products, quantities, a customer, \
delivery city/date, house-size descriptions that need a quantity worked out, bulk/multi-product lists, or a \
follow-up that adjusts or confirms an order discussed earlier ("make it 80", "yes use 27 squares", "add ridge cap").
- "WARRANTY" -- a product, warranty, approval, installation, add-on requirement, eligibility, or contractor-\
certification-tier question; leaks, defects or safety concerns.
- "CONTRACTOR" -- finding, recommending or listing roofing contractors/installers/roofers near a place or for a customer.
- "GENERAL" -- a question about an existing account or order (credit, balance, order status, "show me ORD-77012"), \
inventory/stock by warehouse, product prices or comparisons ("what does HDZ cost per square", "HDZ vs UHDZ"), \
discounts/promotions, or the rep's own orders/commission.
- "CHAT" -- a greeting, thanks, goodbye, asking what you can do, asking for a person, or an unrelated topic. \
A greeting followed by a business question must go to a specialist, not CHAT.

For CHAT, choose chat_intent: "greeting", "thanks", "goodbye", "help", "handoff", or "unrelated".
Tone: "frustrated" if the customer sounds upset, impatient, or has repeated themselves; otherwise "neutral".

Respond with ONLY compact JSON, no prose: {{"route": "ORDER" | "WARRANTY" | "CONTRACTOR" | "GENERAL" | "CHAT", "tone": "neutral" | "frustrated", "chat_intent": string | null}}

{context}

Latest message: "{message}\""""

_HANDOFF_PATTERN = re.compile(
    r"\b(speak|talk|connect|transfer)\w*\s+(?:me\s+)?(to|with)\s+(a|an|the)?\s*(human|person|agent|rep|representative|manager|supervisor|someone)\b"
    r"|\b(real\s+person|human\s+being|manager|supervisor)\b",
    re.IGNORECASE,
)
_GREETING_PATTERN = re.compile(r"(?:hi+|hey+|hello+|good\s+(?:morning|afternoon|evening))(?:\s+(?:there|gaf|assistant))?[\s!.,?]*", re.IGNORECASE)
_ORDER_LOOKUP = re.compile(r"\b(show|look ?up|find|status of|check|pull up|what happened to|where is)\b.*\bORD-\d{3,}\b|\bORD-\d{3,}\b.*\b(status|details|show)\b", re.IGNORECASE)
_CONTRACTOR = re.compile(r"\b(contractors?|installers?|roofers?)\b", re.IGNORECASE)
_NEW_ORDER_WORDS = re.compile(r"\b(order|need|quote|squares?|bundles?|deliver)\b", re.IGNORECASE)

SPECIALIST_LABEL = {
    "order": "Smart Order Agent",
    "warranty": "Product & Warranty Agent",
    "contractor": "Contractor Finder",
    "general": "General Inquiry Handler",
}


async def run_assistant_chat(message: str, location: Optional[str] = None, history: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    if _GREETING_PATTERN.fullmatch(message.strip()):
        classification = {"route": "CHAT", "tone": "neutral", "chat_intent": "greeting"}
    else:
        classification = foundry_client.call_model_json(_ROUTE_PROMPT.format(message=message, context=format_history(history)))
    route = str(classification.get("route", "WARRANTY")).upper()
    tone = "frustrated" if classification.get("tone") == "frustrated" else "neutral"
    handoff = tone == "frustrated" or bool(_HANDOFF_PATTERN.search(message))

    # Deterministic overrides -- never left to the model.
    overrides: list[str] = []
    if _ORDER_LOOKUP.search(message) and not re.search(r"\b(same as|like|reorder|again)\b", message, re.IGNORECASE):
        route, _ = "GENERAL", overrides.append("order-number lookup")
    elif _CONTRACTOR.search(message) and (re.search(r"\b\d{5}\b", message) or re.search(r"\bnear\b|\bin\b|\baround\b", message, re.IGNORECASE)) and not _NEW_ORDER_WORDS.search(message):
        route, _ = "CONTRACTOR", overrides.append("contractor wording with a location")

    if route == "CHAT":
        replies = {
            "greeting": "Hi! I can prepare and price a roofing order, answer product and warranty questions from approved sources, or find certified contractors near a customer. What would you like to do?",
            "thanks": "You're welcome! Anything else for this customer?",
            "goodbye": "Thanks -- come back whenever you need an order priced or a product question answered.",
            "help": "I can: build and price an order (single or bulk, with add-ons and automatic discounts), estimate squares from a house description, answer product/warranty/approval questions from approved documents, find GAF-certified contractors near a ZIP, look up an account's orders or credit, and draft a customer email. Pick a demo use case from the menu to see each one.",
            "handoff": "Understood -- I'll flag this for a human. Please loop in your sales manager or Technical Services, and I'll keep the order details ready.",
            "unrelated": "I can help with roofing orders, pricing, products, warranties and contractors. What would you like to know about those?",
        }
        intent = "handoff" if _HANDOFF_PATTERN.search(message) else classification.get("chat_intent")
        if not isinstance(intent, str):
            intent = "help"
        result: dict[str, Any] = {"routed_to": "chat", "status": "answered", "answer": replies.get(intent, replies["help"]), "sources": [],
                                  "agent_timeline": ["Coordinator handled the conversation"]}
    elif route == "ORDER":
        result = await order_orchestrator.run_order_chat(message, history)
        result["routed_to"] = "order"
    elif route == "CONTRACTOR":
        result = await contractor_orchestrator.run_contractor_search(message, location, history)
        result["routed_to"] = "contractor"
    elif route == "GENERAL":
        result = await general_query_orchestrator.run_general_query_chat(message, history)
        result["routed_to"] = "general"
    else:
        result = await warranty_orchestrator.run_warranty_chat(message, location, history)
        result["routed_to"] = "warranty"

    if result["routed_to"] != "chat":
        label = SPECIALIST_LABEL[result["routed_to"]]
        note = f" (deterministic override: {overrides[0]})" if overrides else ""
        result.setdefault("agent_timeline", []).insert(0, f"Coordinator routed this to the {label}{note}")

    result["tone"] = tone
    result["handoff_suggested"] = handoff
    if handoff:
        result["agent_timeline"].insert(1, "Coordinator flagged this conversation for a human handoff offer")
    return result
