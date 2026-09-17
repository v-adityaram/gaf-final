from fastapi import APIRouter
from pydantic import BaseModel

from app.orchestrators import assistant_orchestrator
from app.services import metrics_service, order_service
from app.services.gaf_realtime import create_realtime_session
from app.services.turn_credentials import generate_turn_credentials

router = APIRouter()


class VoiceSessionResponse(BaseModel):
    success: bool
    client_secret: str | None = None
    realtime_url: str | None = None
    error: str | None = None
    post_connect_update: dict | None = None
    # Present only when TURN_SHARED_SECRET/TURN_DOMAIN are configured (see
    # app/services/turn_credentials.py) -- time-limited, never a standing
    # secret shipped to the browser. None means "no TURN relay configured",
    # not a failure -- the frontend falls back to STUN-only in that case.
    turn: dict | None = None


@router.post("/api/voice/session", response_model=VoiceSessionResponse)
async def voice_session() -> VoiceSessionResponse:
    result = await create_realtime_session()
    return VoiceSessionResponse(**result.model_dump(), turn=generate_turn_credentials())


class VoiceToolRequest(BaseModel):
    function_name: str
    # Present for handle_customer_request
    message: str | None = None
    location: str | None = None
    # Present for confirm_pending_order -- sourced from the model's own
    # prior tool call, never invented (see gaf_realtime.INSTRUCTIONS).
    order_session_id: str | None = None


class VoiceToolResponse(BaseModel):
    success: bool
    data: dict | None = None
    error: str | None = None


@router.post("/api/voice/tool", response_model=VoiceToolResponse)
async def voice_tool(request: VoiceToolRequest) -> VoiceToolResponse:
    if request.function_name == "handle_customer_request":
        if not request.message:
            return VoiceToolResponse(success=False, error="missing_message")
        started_at = metrics_service.start_timer()
        result = await assistant_orchestrator.run_assistant_chat(request.message, request.location)
        # Recorded as its own "Voice" request type (not "Smart Order"/
        # "Warranty"/"Assistant") since the channel -- not the routing
        # outcome -- is what the metrics dashboard distinguishes here.
        metrics_service.record_request(
            request_type="Voice",
            user_request=request.message,
            status=result.get("status", "unknown"),
            model_name=result.get("model"),
            total_latency_ms=metrics_service.elapsed_ms(started_at),
            guardrails=result.get("guardrails"),
        )
        if result.get("routed_to") == "order":
            metrics_service.record_order(result)
        return VoiceToolResponse(success=True, data=result)

    if request.function_name == "confirm_pending_order":
        if not request.order_session_id:
            return VoiceToolResponse(success=False, error="missing_order_session_id")
        # The caller has already verbally confirmed by the time the model calls
        # this tool -- its instructions require surfacing any duplicate/warning
        # first and only calling this after the caller agrees to proceed.
        result = order_service.confirm_session(request.order_session_id, duplicate_acknowledged=True)
        if result.get("status") == "confirmed":
            metrics_service.confirm_order(request.order_session_id)
        return VoiceToolResponse(success=True, data=result)

    return VoiceToolResponse(success=False, error="unknown_function")
