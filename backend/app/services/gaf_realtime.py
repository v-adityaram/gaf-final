"""Realtime voice for the GAF Assistant -- same WebRTC/ephemeral-token
architecture as telecom-assistant's app/services/realtime.py, reusing that
project's own Azure OpenAI resource and realtime deployment (see config.py
for why: gaf-foundry has no realtime model deployed, and standing up a
second one just for this demo would be pure added cost).

One simplification versus telecom-assistant: that app gates response
creation on the browser first receiving a transcript, so it can tell the
model which of several Indian languages the caller just switched to before
it replies. GAF's assistant is English-only, so there's no language
decision to protect -- turn_detection.create_response stays True at both
mint time and post-connect, and the server auto-responds as soon as the
caller stops talking. Transcription is still enabled purely to show a live
caption in the UI.

Tool design mirrors the Coordinator architecture already built for text:
handle_customer_request forwards the caller's own words to
assistant_orchestrator.run_assistant_chat (the exact same routing +
business logic the text Assistant tab uses) and hands the model back
whatever it returned, to speak conversationally. confirm_pending_order is
the spoken equivalent of the text UI's "Confirm Order" button -- it can
only confirm a session id the model was actually given by
handle_customer_request, never one it invents, preserving the same
human-in-the-loop rule the text flow already enforces.
"""

import logging

import httpx
from pydantic import BaseModel

from app.config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_REALTIME_DEPLOYMENT,
    AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT,
    REALTIME_NOISE_REDUCTION_MODE,
    REALTIME_VAD_THRESHOLD,
)

logger = logging.getLogger("gaf_demo.realtime")

TIMEOUT = httpx.Timeout(connect=3.0, read=6.0, write=3.0, pool=3.0)

INSTRUCTIONS = """You are the GAF sales assistant on a live call with a sales rep, helping them
prepare and price roofing orders for their contractor and distributor accounts, answer product,
warranty and approval questions, and find certified contractors near a customer.

You have two tools:
- handle_customer_request(message, location) -- call this for EVERY order, pricing, product/warranty
  or contractor request. Pass the rep's request in your own summary of their words (customer, every
  product line with quantity and unit, delivery details for an order; the product/situation for a
  warranty question; the ZIP or city for contractors). Never answer from memory -- always call this
  tool and speak only what it returns.
- confirm_pending_order(order_session_id) -- call this ONLY after handle_customer_request has
  returned an order with status "ready_for_review" AND the caller has verbally confirmed they want
  to proceed. Use the exact order_session_id you were given; never invent one.

Speak the tool's result conversationally and briefly, suited for a phone call, not a written report:
- If routed_to is "order": summarize the customer, each line (product, colour, quantity), the order
  total after discounts, and the final status in two or three sentences. If status is
  "ready_for_review", ask the rep to confirm before you call confirm_pending_order. If there are
  warnings (duplicate order, delivery method, low inventory, credit), mention them plainly and ask how
  they'd like to proceed. If status is "needs_clarification", ask for exactly what's missing -- and if
  an estimate was proposed, read the proposed squares and ask whether to go with it.
- If routed_to is "warranty": speak the answer field directly. If status is "needs_review", say the
  answer is a draft pending human review. If status is "no_source", say plainly there is no approved
  source and it needs Technical Services. If status is "escalated" or "urgent_escalation", say it is
  being escalated and why.
- If routed_to is "contractor": read the top two or three contractors with certification and rating.
- If routed_to is "general" or "chat": speak the answer field briefly and naturally.

Never invent a product name, SKU, account, price, or warranty fact that isn't in what the tool
returned -- if it isn't in the data, say so plainly rather than guessing.

Keep responses short and conversational. If a request is ambiguous, ask a brief clarifying
question before calling a tool with something you're unsure about."""

REALTIME_TOOLS = [
    {
        "type": "function",
        "name": "handle_customer_request",
        "description": (
            "Send the caller's roofing order or product/warranty request to the backend, which "
            "resolves the customer, product, inventory, credit and warranty data and returns a "
            "grounded result. Always call this instead of answering from memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The caller's request, in your own words -- an order (customer, product, quantity, delivery) or a product/warranty question.",
                },
                "location": {
                    "type": "string",
                    "description": "The caller's city/region if mentioned or already known, used for warranty wind-zone lookups. Omit if unknown.",
                },
            },
            "required": ["message"],
        },
    },
    {
        "type": "function",
        "name": "confirm_pending_order",
        "description": (
            "Confirms an order handle_customer_request already prepared and marked ready for "
            "review, after the caller verbally confirms they want to proceed. Never call this "
            "with an order_session_id you were not given by handle_customer_request."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_session_id": {"type": "string"},
            },
            "required": ["order_session_id"],
        },
    },
]


class RealtimeSessionResult(BaseModel):
    success: bool
    client_secret: str | None = None
    realtime_url: str | None = None
    error: str | None = None
    # Full "session.update" event for the browser to send once connected --
    # present only when transcription is configured. Built from the same
    # _session_config() as the mint-time payload, and always the FULL
    # session (not just the transcription field): Azure's session.update
    # replaces nested objects wholesale rather than deep-merging them
    # (confirmed live on telecom-assistant), so a partial update risks
    # silently resetting the voice/instructions/tools.
    post_connect_update: dict | None = None


def _session_config(transcribe_model: str | None) -> dict:
    audio_input: dict = {
        "turn_detection": {
            "type": "server_vad",
            "threshold": REALTIME_VAD_THRESHOLD,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 750,
            # Always True -- see module docstring: GAF is English-only, so
            # there's no language decision to gate a response on.
            "create_response": True,
        },
        "noise_reduction": {"type": REALTIME_NOISE_REDUCTION_MODE},
    }
    if transcribe_model:
        audio_input["transcription"] = {"model": transcribe_model}

    return {
        "type": "realtime",
        "model": AZURE_OPENAI_REALTIME_DEPLOYMENT,
        "instructions": INSTRUCTIONS,
        "audio": {"input": audio_input, "output": {"voice": "alloy"}},
        "tools": REALTIME_TOOLS,
        "tool_choice": "auto",
    }


async def create_realtime_session() -> RealtimeSessionResult:
    """Mints a short-lived ephemeral token via Azure OpenAI's GA realtime
    endpoint. The long-lived AZURE_OPENAI_API_KEY never leaves this backend;
    only the ephemeral token (and the public realtime_url) go to the browser.
    """
    # Checked explicitly rather than just letting the request below fail --
    # with AZURE_OPENAI_ENDPOINT empty, httpx can't even form a URL, and
    # that used to surface as "realtime_session_unreachable" (an actual
    # network failure) when the real problem is "never configured at all".
    if not (AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY and AZURE_OPENAI_REALTIME_DEPLOYMENT):
        logger.info("realtime_not_configured")
        return RealtimeSessionResult(success=False, error="realtime_not_configured")

    url = f"{AZURE_OPENAI_ENDPOINT}/realtime/client_secrets"

    # Transcription is deliberately excluded from the mint-time payload --
    # Azure's client_secrets endpoint fails to resolve a transcription
    # deployment there (DeploymentNotFound, confirmed live on
    # telecom-assistant with the same resource). Enabled after connecting
    # instead, via post_connect_update below.
    payload = {"session": _session_config(transcribe_model=None)}
    headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        client_secret = data.get("value")
        if not client_secret:
            logger.warning("realtime_session_missing_client_secret")
            return RealtimeSessionResult(success=False, error="realtime_session_invalid_response")

        post_connect_update = None
        if AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT:
            post_connect_update = {
                "type": "session.update",
                "session": _session_config(transcribe_model=AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT),
            }

        return RealtimeSessionResult(
            success=True,
            client_secret=client_secret,
            realtime_url=f"{AZURE_OPENAI_ENDPOINT}/realtime/calls",
            post_connect_update=post_connect_update,
        )

    except httpx.TimeoutException:
        logger.warning("realtime_session_timeout")
        return RealtimeSessionResult(success=False, error="realtime_session_timeout")

    except httpx.HTTPStatusError as exc:
        logger.warning("realtime_session_http_error status=%s", exc.response.status_code)
        return RealtimeSessionResult(success=False, error="realtime_session_error")

    except httpx.RequestError:
        logger.warning("realtime_session_request_error")
        return RealtimeSessionResult(success=False, error="realtime_session_unreachable")

    except ValueError:
        logger.warning("realtime_session_invalid_response")
        return RealtimeSessionResult(success=False, error="realtime_session_invalid_response")
