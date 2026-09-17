import { useEffect, useRef, useState } from "react";
import { confirmOrder, orderChat, recheckOrder, type OrderRecheckFields } from "../api";
import AgentTimeline from "../components/AgentTimeline";
import FeedbackButtons from "../components/FeedbackButtons";
import GuardrailsCard from "../components/GuardrailsCard";
import { SendIcon } from "../components/Icons";
import OrderForm from "../components/OrderForm";
import OrderSummary from "../components/OrderSummary";
import SidePanel from "../components/SidePanel";
import { ProductCardRow } from "../components/ProductCard";
import type { Clarification, GuardrailItem, OrderChatResponse, OrderConfirmResponse, OrderDetails, ProductCard as ProductCardData, RoofEstimate } from "../types";

interface ChatEntry {
  role: "user" | "assistant";
  text: string;
  status?: OrderChatResponse["status"];
  sessionId?: string | null;
  latencyMs?: number;
  details?: OrderDetails | null;
  guardrails?: GuardrailItem[];
  products?: ProductCardData[];
  estimate?: RoofEstimate | null;
  clarification?: Clarification | null;
}

function statusBadge(status?: OrderChatResponse["status"]) {
  if (status === "ready_for_review") return <span className="status-badge green">Ready for review</span>;
  if (status === "blocked") return <span className="status-badge red">Blocked</span>;
  if (status === "needs_clarification") return <span className="status-badge amber">Needs details</span>;
  return null;
}

interface SmartOrderPageProps {
  onActivity?: () => void;
}

export default function SmartOrderPage({ onActivity }: SmartOrderPageProps) {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatLog, setChatLog] = useState<ChatEntry[]>([]);
  const [timeline, setTimeline] = useState<string[]>([]);
  const [confirmedSessions, setConfirmedSessions] = useState<Record<string, OrderConfirmResponse>>({});
  const [confirmingSessionId, setConfirmingSessionId] = useState<string | null>(null);
  const [recheckingIdx, setRecheckingIdx] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatLog, loading]);

  async function handleSubmit(preset?: string) {
    const outgoing = preset ?? message;
    if (!outgoing.trim() || loading) return;
    setMessage("");
    setLoading(true);
    setError(null);
    const history = chatLog.slice(-8).map((e) => ({ role: e.role, text: e.text }));
    setChatLog((log) => [...log, { role: "user", text: outgoing }]);

    const startedAt = performance.now();
    try {
      const response: OrderChatResponse = await orderChat(outgoing, history);
      const latencyMs = performance.now() - startedAt;
      setTimeline(response.agent_timeline);
      setChatLog((log) => [
        ...log,
        {
          role: "assistant",
          text: response.agent_message || "(No response text from the agent.)",
          status: response.status,
          sessionId: response.order_session_id,
          latencyMs,
          details: response.order_details,
          guardrails: response.guardrails,
          products: response.products,
          estimate: response.estimate,
          clarification: response.clarification,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  // Editing a field on the order form and clicking "Recheck Order" updates
  // that same card in place -- it reruns quantity conversion and the
  // inventory/credit/duplicate checks from scratch, rather than appending a
  // new chat message for every edit.
  async function handleRecheck(idx: number, fields: OrderRecheckFields) {
    setRecheckingIdx(idx);
    setError(null);
    const history = chatLog.slice(0, idx).slice(-8).map((e) => ({ role: e.role, text: e.text }));
    try {
      const response = await recheckOrder(fields, history);
      setTimeline(response.agent_timeline);
      setChatLog((log) =>
        log.map((entry, i) =>
          i === idx
            ? {
                ...entry,
                text: response.agent_message || entry.text,
                status: response.status,
                sessionId: response.order_session_id,
                details: response.order_details,
                guardrails: response.guardrails,
                products: response.products,
                clarification: response.clarification,
              }
            : entry
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not recheck order.");
    } finally {
      setRecheckingIdx(null);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  async function handleConfirm(sessionId: string, duplicateAcknowledged: boolean) {
    setConfirmingSessionId(sessionId);
    try {
      const response = await confirmOrder(sessionId, duplicateAcknowledged);
      // The backend rejects this (credit hold, unacknowledged duplicate) by
      // returning status "error" with a 200 -- only mark it confirmed when
      // it actually says "confirmed".
      if (response.status === "confirmed") {
        setConfirmedSessions((prev) => ({ ...prev, [sessionId]: response }));
        onActivity?.();
      } else {
        setError(response.message || "Could not confirm order.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm order.");
    } finally {
      setConfirmingSessionId(null);
    }
  }

  return (
    <div className="workspace">
      <section className="panel chat-shell" aria-label="Smart Order Agent conversation">
        <div className="chat-shell-header">
          <span className="status-dot" />
          <span className="name">Smart Order Agent</span>
          <span className="role">· prices every line, applies discounts, checks stock, credit &amp; duplicates</span>
        </div>

        <div className="chat-messages">
          {chatLog.length === 0 && (
            <div className="chat-empty-state">
              <p>Describe an order in plain language — customer, product, quantity, delivery city and date — and it will be looked up and prepared for your review.</p>
            </div>
          )}

          {chatLog.map((entry, idx) => (
            <div key={idx} className={`chat-bubble-row ${entry.role} ${entry.details ? "has-form" : ""}`}>
              {/* The order form shows its own status badge -- only show this
                  one for plain-text replies (clarifications, chat prose). */}
              {entry.role === "assistant" && !entry.details && statusBadge(entry.status) && <div className="bubble-meta">{statusBadge(entry.status)}</div>}
              <div className={entry.role === "user" ? "chat-bubble user" : "chat-bubble assistant"}>
                {entry.role === "user" ? (
                  <span className="bubble-text">{entry.text}</span>
                ) : entry.details ? (
                  <OrderForm
                    details={entry.details}
                    status={entry.status as "ready_for_review" | "blocked"}
                    sessionId={entry.sessionId}
                    rechecking={recheckingIdx === idx}
                    confirming={!!entry.sessionId && confirmingSessionId === entry.sessionId}
                    confirmed={!!(entry.sessionId && confirmedSessions[entry.sessionId])}
                    confirmMessage={entry.sessionId ? confirmedSessions[entry.sessionId]?.message : null}
                    onRecheck={(fields) => handleRecheck(idx, fields)}
                    onConfirm={(duplicateAcknowledged) => entry.sessionId && handleConfirm(entry.sessionId, duplicateAcknowledged)}
                  />
                ) : entry.status === "needs_clarification" ? (
                  <span className="bubble-text">{entry.text}</span>
                ) : (
                  <OrderSummary text={entry.text} />
                )}
              </div>
              {entry.role === "assistant" && entry.products && entry.products.length > 0 && <ProductCardRow products={entry.products} />}
              {entry.role === "assistant" && idx === chatLog.length - 1 && entry.clarification?.quick_replies?.length ? (
                <div className="quick-replies" aria-label="Suggested replies">
                  {entry.clarification.quick_replies.map((reply) => (
                    <button key={reply} className="chip" onClick={() => handleSubmit(reply)} disabled={loading}>
                      {reply}
                    </button>
                  ))}
                </div>
              ) : null}
              {entry.role === "assistant" && <GuardrailsCard items={entry.guardrails} />}
              {entry.role === "assistant" && (
                <div className="bubble-footer">
                  {entry.latencyMs !== undefined && <span className="latency-badge">{(entry.latencyMs / 1000).toFixed(1)}s</span>}
                  <FeedbackButtons context={{ route: "order", status: entry.status ?? null, user_message: chatLog[idx - 1]?.text ?? null, assistant_message: entry.text }} />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="chat-bubble-row assistant">
              <div className="chat-bubble assistant">
                <span className="thinking" aria-label="Thinking">
                  <span />
                  <span />
                  <span />
                </span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="composer-wrap">
          {error && (
            <div className="error-banner" style={{ marginBottom: 10 }}>
              {error}
            </div>
          )}
          <div className="chat-input-bar">
            <textarea
              rows={1}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message the Smart Order Agent…"
              aria-label="Message"
            />
            <button className="icon-button primary" onClick={() => handleSubmit()} disabled={loading || !message.trim()} aria-label="Send">
              <SendIcon size={17} />
            </button>
          </div>
        </div>
      </section>

      <div className="side-stack">
        <SidePanel title="Agent activity">
          {timeline.length > 0 ? (
            <AgentTimeline steps={timeline} />
          ) : (
            <div className="panel-hint">Each step the agent takes for the latest message shows up here.</div>
          )}
        </SidePanel>
      </div>
    </div>
  );
}
