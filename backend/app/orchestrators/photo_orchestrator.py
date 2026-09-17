"""Roof-photo intake: one vision call describes what is visible, then plain
Python turns that into a question for the Product & Warranty Advisor,
which answers from approved data exactly as it would for a typed question.

The vision model is used only as eyes, never as the authority: it must not
claim a product identification with certainty, and anything it flags as a
possible leak/defect is forced through the advisor's existing URGENT
escalation path deterministically (the composed question carries the
trigger words the safety-net regex looks for), rather than trusting the
model to classify severity."""

from typing import Any, Optional

from app import foundry_client
from app.orchestrators import warranty_orchestrator

_VISION_PROMPT = """You are helping a GAF roofing customer-service rep look at a photo a customer sent.

Describe ONLY what is actually visible. Do not guess brand names or product lines unless a label, \
wrapper, or printed name is legible ON A PHYSICAL PRODUCT in the image. Do not diagnose a cause \
you cannot see.

Respond with ONLY compact JSON, no prose:
{{
  "isRoofingRelated": boolean,          // true ONLY for a photo of a physical roof, shingles, flashing, underlayment, or roofing packaging. Screenshots, documents, chat windows, text, or unrelated objects are false -- even if they mention roofing words.
  "whatIsVisible": string,              // one or two plain sentences
  "possibleIssues": [string],           // e.g. "lifted shingle tabs", "missing granules", "exposed nails" -- empty if none visible
  "urgentSigns": boolean,               // true ONLY if you can see active water intrusion, a hole, or structural damage
  "productGuess": string | null,        // only if a legible label/name is visible; otherwise null
  "questionForAdvisor": string          // one question a rep should ask the warranty advisor about what's seen, phrased generically
}}

Rep's note (may be empty): "{note}\""""


async def run_photo_intake(image_data_url: str, note: Optional[str], location: Optional[str]) -> dict[str, Any]:
    timeline = ["Photo Analyst described what is visible in the image"]
    analysis = foundry_client.call_model_vision_json(_VISION_PROMPT.format(note=note or ""), image_data_url)

    if not analysis.get("isRoofingRelated", False):
        timeline.append("Image does not appear to show roofing -- no advisor question asked")
        return {"status": "not_a_roof", "analysis": analysis, "question": None, "warranty": None, "agent_timeline": timeline}

    question = (analysis.get("questionForAdvisor") or "What should the customer do about what is visible in this roof photo?").strip()
    product = analysis.get("productGuess")
    if product:
        question = f"For {product}: {question}"
    if analysis.get("urgentSigns"):
        # Carries the safety-net trigger words so the advisor's regex forces
        # URGENT_ESCALATION no matter how the classifier reads it.
        question = f"Possible leak or product defect seen in a customer photo. {question}"
        timeline.append("Urgent signs flagged in the photo -- routing as urgent")

    warranty = await warranty_orchestrator.run_warranty_chat(question, location)
    timeline.extend(warranty.get("agent_timeline", []))
    return {"status": "analyzed", "analysis": analysis, "question": question, "warranty": warranty, "agent_timeline": timeline}
