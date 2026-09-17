"""Drafts the professional customer email a rep sends after the
conversation -- order summary, pricing, next steps -- grounded strictly in
the transcript: the model may only restate what is literally there, never
add prices, dates, availability, or commitments that weren't said."""

from typing import Any, Optional

from app import foundry_client
from app.orchestrators.history import format_history

_EMAIL_PROMPT = """Draft a professional, ready-to-send email from a GAF sales representative to their customer, \
following up on the conversation below.

Use ONLY facts that appear literally in the transcript. Do not add prices, delivery dates, stock figures, \
warranty terms, discounts or commitments that are not stated there. If the transcript is too thin, write a short \
courteous check-in instead of inventing content. Never mention internal tooling, guardrails or AI.

Format, plain text (no markdown):
Subject: <clear, specific subject line>

Dear <customer contact or company name if stated, otherwise "Customer">,

<one-sentence opening that references the conversation>

<if an order was prepared: a short itemised summary -- product, colour, quantity, unit; the order total and any \
discounts exactly as stated; delivery city/date as stated; and the order's current status (e.g. awaiting confirmation, on hold)>

<if a product/warranty answer was given: restate it in one or two sentences and name the source document if one was cited>

<if anything is still needed from the customer, list it as "To proceed, we need:" followed by short bullet lines starting with "- ">

Next steps: <one line>

Best regards,
{rep_name}
{rep_title}
{rep_phone}

Transcript:
{transcript}"""


def run_recap(history: list[dict[str, Any]], rep: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    transcript = format_history(history)
    if not transcript:
        return {"recap": "Nothing to draft yet — have a conversation with the customer first.", "agent_timeline": ["No conversation to draft from"]}
    rep = rep or {}
    email = foundry_client.call_model(_EMAIL_PROMPT.format(
        transcript=transcript, rep_name=rep.get("name") or "GAF Sales Representative",
        rep_title=rep.get("title") or "Territory Sales", rep_phone=rep.get("phone") or "",
    )).strip()
    return {"recap": email, "agent_timeline": ["Email Writer drafted a customer email from the transcript only"]}
