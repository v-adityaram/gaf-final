from typing import Any, Optional

from pydantic import BaseModel, Field


class HistoryTurn(BaseModel):
    role: str  # "user" | "assistant"
    text: str


class OrderChatRequest(BaseModel):
    message: str
    history: list[HistoryTurn] = []


class OrderConfirmRequest(BaseModel):
    order_session_id: str
    duplicate_acknowledged: bool = False


class OrderLineInput(BaseModel):
    """One editable line on the order form. sku is authoritative when
    present; product/colour are the fuzzy fallback."""

    sku: Optional[str] = None
    product: Optional[str] = None
    colour: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    included: bool = True
    source: str = "customer"  # "customer" | "add_on"
    add_on_rule: Optional[str] = None


class OrderRecheckRequest(BaseModel):
    """The editable order form, submitted as already-structured fields (no
    free text to extract). When `lines` is given it is authoritative and
    the legacy single-product fields are ignored."""

    customer_name: Optional[str] = None
    customer_id: Optional[str] = None
    product: Optional[str] = None
    colour: Optional[str] = None
    sku: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    lines: list[OrderLineInput] = []
    include_add_ons: Optional[bool] = None
    delivery_city: Optional[str] = None
    delivery_date: Optional[str] = None
    delivery_method: Optional[str] = None
    history: list[HistoryTurn] = []


class WarrantyChatRequest(BaseModel):
    question: str
    location: Optional[str] = None
    history: list[HistoryTurn] = []


class OrderChatResponse(BaseModel):
    status: str
    order_session_id: Optional[str] = None
    agent_message: Optional[str] = None
    agent_timeline: list[str] = []
    # Structured, editable-form-ready fields (see order_orchestrator's
    # order_details dict: lines[], pricing{}, add-ons, checks[]).
    order_details: Optional[dict[str, Any]] = None
    # Roof-size estimate when the customer described a house, and the
    # structured clarification (type + quick replies) when one is needed.
    estimate: Optional[dict[str, Any]] = None
    clarification: Optional[dict[str, Any]] = None
    # Product cards (swatch, price, badges) for the lines on the order.
    products: list[dict[str, Any]] = []
    guardrails: list[dict[str, str]] = []
    provider: Optional[str] = None
    model: Optional[str] = None


class OrderConfirmResponse(BaseModel):
    status: str
    message: str
    erp_submission: Optional[str] = None
    confirmation: Optional[dict[str, Any]] = None


class WarrantyChatResponse(BaseModel):
    status: str  # answered | needs_review | no_source | escalated | urgent_escalation
    answer: Optional[str] = None
    sources: list[dict[str, Any]] = []
    escalation: Optional[dict[str, Any]] = None
    agent_timeline: list[str] = []
    guardrails: list[dict[str, str]] = []
    # Deterministic 0-100 score; >= 95 auto-answers, otherwise the draft is
    # queued for a human (review.review_id).
    confidence: Optional[int] = None
    review: Optional[dict[str, Any]] = None
    products: list[dict[str, Any]] = []
    provider: Optional[str] = None
    model: Optional[str] = None


class AssistantChatRequest(BaseModel):
    message: str
    location: Optional[str] = None
    history: list[HistoryTurn] = []


class AssistantChatResponse(BaseModel):
    # "order" | "warranty" | "contractor" | "general" | "chat"
    routed_to: str
    status: str
    agent_message: Optional[str] = None
    order_session_id: Optional[str] = None
    order_details: Optional[dict[str, Any]] = None
    estimate: Optional[dict[str, Any]] = None
    clarification: Optional[dict[str, Any]] = None
    answer: Optional[str] = None
    sources: list[dict[str, Any]] = []
    escalation: Optional[dict[str, Any]] = None
    confidence: Optional[int] = None
    review: Optional[dict[str, Any]] = None
    contractors: list[dict[str, Any]] = []
    location_resolved: Optional[dict[str, Any]] = Field(default=None, alias="location")
    products: list[dict[str, Any]] = []
    order: Optional[dict[str, Any]] = None
    agent_timeline: list[str] = []
    guardrails: list[dict[str, str]] = []
    tone: str = "neutral"
    handoff_suggested: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None

    model_config = {"populate_by_name": True}


class FeedbackRequest(BaseModel):
    rating: str  # "up" | "down"
    route: Optional[str] = None
    status: Optional[str] = None
    user_message: Optional[str] = None
    assistant_message: Optional[str] = None
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    status: str
    feedback_id: str


class FeedbackSummary(BaseModel):
    up: int
    down: int
    total: int
    recent: list[dict[str, Any]] = []


class EmailDraftRequest(BaseModel):
    history: list[HistoryTurn]
    location: Optional[str] = None
    rep_id: Optional[str] = None


class EmailDraftResponse(BaseModel):
    recap: str
    agent_timeline: list[str] = []


class EmailIntakeRequest(BaseModel):
    email_ids: list[str] = Field(min_length=1, max_length=10)
    location: Optional[str] = None
    history: list[HistoryTurn] = []


class EmailIntakeResponse(BaseModel):
    items: list[dict[str, Any]]
    provider: Optional[str] = None
    model: Optional[str] = None


class ReviewResolveRequest(BaseModel):
    decision: str  # approve | edit | reject
    final_answer: Optional[str] = None
    reviewer: Optional[str] = None


class PhotoRequest(BaseModel):
    image_data_url: str = Field(min_length=32)
    note: Optional[str] = None
    location: Optional[str] = None


class PhotoResponse(BaseModel):
    status: str  # "analyzed" | "not_a_roof"
    analysis: dict[str, Any]
    question: Optional[str] = None
    warranty: Optional[WarrantyChatResponse] = None
    agent_timeline: list[str] = []
