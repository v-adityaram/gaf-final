import type {
  AssistantChatResponse,
  ConfirmedOrderRecord,
  Contractor,
  EmailDraftResponse,
  EmailIntakeItem,
  FeedbackPayload,
  HistoryTurn,
  InboxEmail,
  MetricsRequestRecord,
  MetricsSummary,
  OrderChatResponse,
  OrderConfirmResponse,
  OrderHistoryRecord,
  RepDashboard,
  ResolvedLocation,
  ReviewItem,
  SalesRep,
  UseCase,
  WarrantyChatResponse,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8001";

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = "";
    try {
      const errorBody = await response.json();
      detail = errorBody?.detail ? `: ${errorBody.detail}` : "";
    } catch {
      // response wasn't JSON
    }
    throw new Error(`Request to ${path} failed with status ${response.status}${detail}`);
  }
  return (await response.json()) as T;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) throw new Error(`Request to ${path} failed with status ${response.status}`);
  return response.json();
}

// ------------------------------------------------------------------ orders

export function orderChat(message: string, history: HistoryTurn[] = []): Promise<OrderChatResponse> {
  return postJson<OrderChatResponse>("/api/order/chat", { message, history });
}

export interface OrderLineInput {
  sku?: string | null;
  product?: string | null;
  colour?: string | null;
  quantity?: number | null;
  unit?: string | null;
  included?: boolean;
  source?: "customer" | "add_on";
  add_on_rule?: string | null;
}

// The editable order form's fields, submitted as-is (already structured --
// no free text to extract). `lines` is authoritative when present.
export interface OrderRecheckFields {
  customer_name?: string | null;
  customer_id?: string | null;
  product?: string | null;
  colour?: string | null;
  sku?: string | null;
  quantity?: number | null;
  unit?: string | null;
  lines?: OrderLineInput[];
  include_add_ons?: boolean | null;
  delivery_city?: string | null;
  delivery_date?: string | null;
  delivery_method?: string | null;
}

export function recheckOrder(fields: OrderRecheckFields, history: HistoryTurn[] = []): Promise<OrderChatResponse> {
  return postJson<OrderChatResponse>("/api/order/recheck", { ...fields, history });
}

export function confirmOrder(orderSessionId: string, duplicateAcknowledged: boolean): Promise<OrderConfirmResponse> {
  return postJson<OrderConfirmResponse>("/api/order/confirm", { order_session_id: orderSessionId, duplicate_acknowledged: duplicateAcknowledged });
}

// ---------------------------------------------------------------- warranty

export function warrantyChat(question: string, location?: string, history: HistoryTurn[] = []): Promise<WarrantyChatResponse> {
  return postJson<WarrantyChatResponse>("/api/warranty/chat", { question, location, history });
}

export async function getReviews(status?: string): Promise<{ reviews: ReviewItem[]; threshold: number }> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return getJson(`/api/reviews${query}`);
}

export function resolveReview(reviewId: string, decision: "approve" | "edit" | "reject", finalAnswer?: string | null, reviewer?: string | null): Promise<ReviewItem> {
  return postJson<ReviewItem>(`/api/reviews/${encodeURIComponent(reviewId)}/resolve`, { decision, final_answer: finalAnswer ?? null, reviewer: reviewer ?? null });
}

// --------------------------------------------------------------- assistant

export function assistantChat(message: string, location?: string, history: HistoryTurn[] = []): Promise<AssistantChatResponse> {
  return postJson<AssistantChatResponse>("/api/assistant/chat", { message, location, history });
}

export function draftEmail(history: HistoryTurn[], repId?: string | null, location?: string): Promise<EmailDraftResponse> {
  return postJson<EmailDraftResponse>("/api/assistant/draft-email", { history, location, rep_id: repId ?? null });
}

export function sendFeedback(payload: FeedbackPayload): Promise<{ status: string; feedback_id: string }> {
  return postJson("/api/feedback", payload);
}

// ------------------------------------------------------------- email agent

export async function getInbox(repId?: string | null): Promise<InboxEmail[]> {
  const query = repId ? `?rep_id=${encodeURIComponent(repId)}` : "";
  const payload = await getJson<{ emails: InboxEmail[] }>(`/api/inbox${query}`);
  return payload.emails;
}

export async function emailIntake(emailIds: string[], history: HistoryTurn[] = [], location?: string): Promise<EmailIntakeItem[]> {
  const payload = await postJson<{ items: EmailIntakeItem[] }>("/api/email/intake", { email_ids: emailIds, history, location });
  return payload.items;
}

// ------------------------------------------------------------- contractors

export function getContractors(params: { zip?: string; city?: string; radius?: number; limit?: number; minTier?: string }): Promise<{ location: ResolvedLocation; radiusMiles: number; radiusExpanded: boolean; contractors: Contractor[] }> {
  const query = new URLSearchParams();
  if (params.zip) query.set("zip", params.zip);
  if (params.city) query.set("city", params.city);
  if (params.radius) query.set("radius", String(params.radius));
  if (params.limit) query.set("limit", String(params.limit));
  if (params.minTier) query.set("min_tier", params.minTier);
  return getJson(`/api/contractors?${query.toString()}`);
}

// --------------------------------------------------------------- sales reps

export async function getReps(): Promise<SalesRep[]> {
  const payload = await getJson<{ reps: SalesRep[] }>("/api/reps");
  return payload.reps;
}

export function getRepDashboard(repId: string): Promise<RepDashboard> {
  return getJson<RepDashboard>(`/api/reps/${encodeURIComponent(repId)}/dashboard`);
}

// ------------------------------------------------------------- demo helpers

export async function getUseCases(): Promise<UseCase[]> {
  const payload = await getJson<{ useCases: UseCase[] }>("/api/demo/use-cases");
  return payload.useCases;
}

export async function checkHealth(): Promise<{ status: string; foundry_configured: boolean; voice_configured: boolean; data_source?: string }> {
  return getJson("/api/health");
}

// ------------------------------------------------------------------ metrics

export function getMetricsSummary(): Promise<MetricsSummary> {
  return getJson<MetricsSummary>("/api/metrics/summary");
}

export async function getMetricsRequests(limit = 100): Promise<MetricsRequestRecord[]> {
  const payload = await getJson<{ requests: MetricsRequestRecord[] }>(`/api/metrics/requests?limit=${limit}`);
  return payload.requests;
}

export async function getMetricsOrders(status = "All", limit = 100): Promise<OrderHistoryRecord[]> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (status !== "All") query.set("status", status);
  const payload = await getJson<{ orders: OrderHistoryRecord[] }>(`/api/metrics/orders?${query.toString()}`);
  return payload.orders;
}

export async function getConfirmedOrders(limit = 100, repId?: string | null): Promise<ConfirmedOrderRecord[]> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (repId) query.set("rep_id", repId);
  const payload = await getJson<{ confirmed_orders: ConfirmedOrderRecord[] }>(`/api/orders/confirmed?${query.toString()}`);
  return payload.confirmed_orders;
}
