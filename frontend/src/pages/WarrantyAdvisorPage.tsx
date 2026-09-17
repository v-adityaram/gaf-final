import { useEffect, useRef, useState } from "react";
import { warrantyChat } from "../api";
import AgentTimeline from "../components/AgentTimeline";
import FeedbackButtons from "../components/FeedbackButtons";
import GuardrailsCard from "../components/GuardrailsCard";
import { SendIcon } from "../components/Icons";
import SidePanel from "../components/SidePanel";
import SourceCard from "../components/SourceCard";
import ConfidenceMeter from "../components/ConfidenceMeter";
import { ProductCardRow } from "../components/ProductCard";
import type { GuardrailItem, ProductCard as ProductCardData, ReviewInfo, Source, WarrantyChatResponse } from "../types";

interface ChatEntry {
  role: "user" | "assistant";
  status?: WarrantyChatResponse["status"];
  text: string;
  latencyMs?: number;
  guardrails?: GuardrailItem[];
  confidence?: number | null;
  review?: ReviewInfo | null;
  products?: ProductCardData[];
}

function statusBadge(status?: WarrantyChatResponse["status"], confidence?: number | null) {
  if (status === "needs_review") return <span className="status-badge amber">Pending human review</span>;
  if (status === "answered" && confidence != null) return <span className="status-badge green">Auto-answered · {confidence}%</span>;
  if (status === "urgent_escalation") return <span className="status-badge red">Urgent escalation</span>;
  if (status === "escalated") return <span className="status-badge amber">Escalated</span>;
  if (status === "no_source") return <span className="status-badge amber">No approved source</span>;
  return null;
}

function bubbleClass(entry: ChatEntry): string {
  if (entry.role === "user") return "chat-bubble user";
  if (entry.status === "urgent_escalation") return "chat-bubble urgent";
  if (entry.status === "escalated") return "chat-bubble escalation";
  if (entry.status === "no_source") return "chat-bubble no-source";
  if (entry.status === "needs_review") return "chat-bubble review";
  return "chat-bubble assistant";
}

interface WarrantyAdvisorPageProps {
  onActivity?: () => void;
}

export default function WarrantyAdvisorPage({ onActivity }: WarrantyAdvisorPageProps) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatLog, setChatLog] = useState<ChatEntry[]>([]);
  const [latestSources, setLatestSources] = useState<Source[]>([]);
  const [timeline, setTimeline] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatLog, loading]);

  async function handleAsk() {
    if (!question.trim() || loading) return;
    const outgoing = question;
    setQuestion("");
    setLoading(true);
    setError(null);
    const history = chatLog.slice(-8).map((e) => ({ role: e.role, text: e.text }));
    setChatLog((log) => [...log, { role: "user", text: outgoing }]);

    const startedAt = performance.now();
    try {
      const response = await warrantyChat(outgoing, undefined, history);
      const latencyMs = performance.now() - startedAt;
      setTimeline(response.agent_timeline);

      let text = response.answer || "";
      if (response.status === "urgent_escalation") {
        text = `URGENT ESCALATION — escalated to ${response.escalation?.destination || "Technical Services"}: ${response.escalation?.reason || ""}`;
      } else if (response.status === "escalated") {
        text = `Expert Review Required — escalated to ${response.escalation?.destination || "Technical Services"}: ${response.escalation?.reason || ""}`;
      } else if (response.status === "no_source") {
        text = "No approved source available — answer withheld.";
      }

      setChatLog((log) => [...log, { role: "assistant", status: response.status, text, latencyMs, guardrails: response.guardrails, confidence: response.confidence, review: response.review, products: response.products }]);
      setLatestSources(response.sources || []);
      onActivity?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  }

  return (
    <div className="workspace">
      <section className="panel chat-shell" aria-label="Product and Warranty Agent conversation">
        <div className="chat-shell-header">
          <span className="status-dot" />
          <span className="name">Product &amp; Warranty Agent</span>
          <span className="role">· grounded in approved documents; auto-answers at 95%+ confidence, otherwise queued for a human</span>
        </div>

        <div className="chat-messages">
          {chatLog.length === 0 && (
            <div className="chat-empty-state">
              <p>Ask a product or warranty question. Answers come only from approved documentation — anything else is escalated to Technical Services instead of guessed.</p>
            </div>
          )}

          {chatLog.map((entry, idx) => (
            <div key={idx} className={`chat-bubble-row ${entry.role}`}>
              {entry.role === "assistant" && statusBadge(entry.status, entry.confidence) && <div className="bubble-meta">{statusBadge(entry.status, entry.confidence)}</div>}
              <div className={bubbleClass(entry)}>
                <span className="bubble-text">
                  {entry.status === "needs_review" && <span className="review-flag">Draft -- pending human review. </span>}
                  {entry.text}
                </span>
              </div>
              {entry.role === "assistant" && entry.confidence != null && (entry.status === "answered" || entry.status === "needs_review") && <ConfidenceMeter confidence={entry.confidence} review={entry.review} />}
              {entry.role === "assistant" && entry.products && entry.products.length > 0 && <ProductCardRow products={entry.products} />}
              {entry.role === "assistant" && <GuardrailsCard items={entry.guardrails} />}
              {entry.role === "assistant" && (
                <div className="bubble-footer">
                  {entry.latencyMs !== undefined && <span className="latency-badge">{(entry.latencyMs / 1000).toFixed(1)}s</span>}
                  <FeedbackButtons context={{ route: "warranty", status: entry.status ?? null, user_message: chatLog[idx - 1]?.text ?? null, assistant_message: entry.text }} />
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
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask the Product & Warranty Agent…"
              aria-label="Question"
            />
            <button className="icon-button primary" onClick={handleAsk} disabled={loading || !question.trim()} aria-label="Send">
              <SendIcon size={17} />
            </button>
          </div>
        </div>
      </section>

      <div className="side-stack">
        <SidePanel title="Sources">
          {latestSources.length > 0 ? (
            <div className="bubble-sources" style={{ marginTop: 0 }}>
              {latestSources.map((source) => (
                <SourceCard key={source.document_id} source={source} />
              ))}
            </div>
          ) : (
            <div className="panel-hint">Cited documents for the latest answer appear here.</div>
          )}
        </SidePanel>
        <SidePanel title="Agent activity">
          {timeline.length > 0 ? (
            <AgentTimeline steps={timeline} />
          ) : (
            <div className="panel-hint">Each step the agent takes for the latest question shows up here.</div>
          )}
        </SidePanel>
      </div>
    </div>
  );
}
