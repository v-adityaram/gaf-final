import { useEffect, useRef, useState } from "react";
import { assistantChat, checkHealth, confirmOrder, draftEmail, emailIntake, recheckOrder, type OrderRecheckFields } from "../api";
import AgentTimeline from "../components/AgentTimeline";
import ConfidenceMeter from "../components/ConfidenceMeter";
import { ContractorList } from "../components/ContractorCard";
import FeedbackButtons from "../components/FeedbackButtons";
import GuardrailsCard from "../components/GuardrailsCard";
import { CheckIcon, CopyIcon, MailIcon, MicIcon, PhoneIcon, SendIcon, SparkIcon, SpeakerIcon, StopIcon, UserIcon } from "../components/Icons";
import OrderForm from "../components/OrderForm";
import OrderSummary from "../components/OrderSummary";
import { ProductCardRow } from "../components/ProductCard";
import SidePanel from "../components/SidePanel";
import SourceCard from "../components/SourceCard";
import { useGafVoice } from "../hooks/useGafVoice";
import type {
  AssistantChatResponse,
  Clarification,
  Contractor,
  GuardrailItem,
  HistoryTurn,
  OrderConfirmResponse,
  OrderDetails,
  ProductCard as ProductCardData,
  ResolvedLocation,
  ReviewInfo,
  RoofEstimate,
  RoutedTo,
  SalesRep,
  Source,
} from "../types";

interface ChatEntry {
  role: "user" | "assistant";
  text: string;
  voice?: boolean;
  fromEmail?: { fromName: string; subject: string; emailId: string } | null;
  routedTo?: RoutedTo;
  status?: string;
  sessionId?: string | null;
  sources?: Source[];
  escalation?: AssistantChatResponse["escalation"];
  latencyMs?: number;
  details?: OrderDetails | null;
  guardrails?: GuardrailItem[];
  products?: ProductCardData[];
  contractors?: Contractor[];
  location?: ResolvedLocation | null;
  estimate?: RoofEstimate | null;
  clarification?: Clarification | null;
  confidence?: number | null;
  review?: ReviewInfo | null;
}

function routeLabel(routedTo?: RoutedTo) {
  if (routedTo === "chat") return "Coordinator";
  if (routedTo === "order") return "Smart Order Agent";
  if (routedTo === "warranty") return "Product & Warranty Agent";
  if (routedTo === "contractor") return "Contractor Finder";
  if (routedTo === "general") return "General Inquiry";
  return null;
}

function statusBadge(entry: ChatEntry) {
  if (entry.routedTo === "order") {
    if (entry.status === "ready_for_review") return <span className="status-badge green">Ready for review</span>;
    if (entry.status === "blocked") return <span className="status-badge red">Blocked</span>;
    if (entry.status === "needs_clarification") return <span className="status-badge amber">{entry.clarification?.type === "estimate_confirmation" ? "Estimate -- confirm" : "Needs details"}</span>;
  }
  if (entry.routedTo === "warranty" || entry.routedTo === "general" || entry.routedTo === "contractor") {
    if (entry.status === "urgent_escalation") return <span className="status-badge red">Urgent escalation</span>;
    if (entry.status === "escalated") return <span className="status-badge amber">Escalated</span>;
    if (entry.status === "no_source") return <span className="status-badge amber">No approved source</span>;
    if (entry.status === "needs_review") return <span className="status-badge amber">Pending human review</span>;
    if (entry.status === "answered" && entry.confidence != null) return <span className="status-badge green">Auto-answered · {entry.confidence}%</span>;
  }
  return null;
}

function hasOrderForm(entry: ChatEntry): boolean {
  return entry.role === "assistant" && entry.routedTo === "order" && !entry.voice && !!entry.details;
}

function bubbleClass(entry: ChatEntry) {
  if (entry.role === "user") return "chat-bubble user";
  if (entry.status === "urgent_escalation") return "chat-bubble urgent";
  if (entry.status === "escalated") return "chat-bubble escalation";
  if (entry.status === "no_source") return "chat-bubble no-source";
  if (entry.status === "needs_review") return "chat-bubble review";
  return "chat-bubble assistant";
}

function answerText(r: { status: string; answer?: string | null; escalation?: { destination?: string; reason?: string } | null }): string {
  if (r.status === "urgent_escalation") return `URGENT ESCALATION -- escalated to ${r.escalation?.destination || "Technical Services"}: ${r.escalation?.reason || ""}`;
  if (r.status === "escalated") return `Expert Review Required -- escalated to ${r.escalation?.destination || "Technical Services"}: ${r.escalation?.reason || ""}`;
  if (r.status === "no_source") return "No approved source available -- answer withheld.";
  return r.answer || "";
}

function responseTextFor(response: AssistantChatResponse): string {
  if (response.routed_to === "order") return response.agent_message || "(No response text from the agent.)";
  return answerText(response);
}

function entryFromResponse(response: AssistantChatResponse, latencyMs?: number): ChatEntry {
  return {
    role: "assistant",
    text: responseTextFor(response),
    routedTo: response.routed_to,
    status: response.status,
    sessionId: response.order_session_id,
    sources: response.sources,
    escalation: response.escalation,
    latencyMs,
    details: response.order_details,
    guardrails: response.guardrails,
    products: response.products,
    contractors: response.contractors,
    location: response.location,
    estimate: response.estimate,
    clarification: response.clarification,
    confidence: response.confidence,
    review: response.review,
  };
}

function EstimateCard({ estimate }: { estimate: RoofEstimate }) {
  if (estimate.status !== "ok") return null;
  return (
    <div className="estimate-card" aria-label="Roof estimate">
      <div className="estimate-grid">
        {estimate.footprint_sqft != null && <div><dt>Footprint</dt><dd>{estimate.footprint_sqft.toLocaleString()} sq ft</dd></div>}
        {estimate.pitch && <div><dt>Pitch</dt><dd>{estimate.pitch} (x{estimate.pitch_factor})</dd></div>}
        {estimate.roof_sqft != null && <div><dt>Roof area</dt><dd>{estimate.roof_sqft.toLocaleString()} sq ft</dd></div>}
        {estimate.order_sqft != null && <div><dt>+{estimate.waste_percent}% waste</dt><dd>{estimate.order_sqft.toLocaleString()} sq ft</dd></div>}
        <div className="total"><dt>Order</dt><dd>{estimate.squares} squares</dd></div>
      </div>
      {estimate.assumptions && estimate.assumptions.length > 0 && <div className="estimate-assumptions">Assumptions: {estimate.assumptions.join("; ")}</div>}
    </div>
  );
}

interface AssistantPageProps {
  active: boolean;
  rep: SalesRep | null;
  pendingPrompt: { text: string; nonce: number } | null;
  emailRequest: { ids: string[]; nonce: number } | null;
  onEmailsProcessed: (ids: string[]) => void;
  callRequest: number;
  onCallStateChange: (active: boolean) => void;
  onActivity: () => void;
}

export default function AssistantPage({ active, rep, pendingPrompt, emailRequest, onEmailsProcessed, callRequest, onCallStateChange, onActivity }: AssistantPageProps) {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chatLog, setChatLog] = useState<ChatEntry[]>([]);
  const [timeline, setTimeline] = useState<string[]>([]);
  const [handoff, setHandoff] = useState(false);
  const [confirmedSessions, setConfirmedSessions] = useState<Record<string, OrderConfirmResponse>>({});
  const [confirmingSessionId, setConfirmingSessionId] = useState<string | null>(null);
  const [recheckingIdx, setRecheckingIdx] = useState<number | null>(null);
  const [emailDraft, setEmailDraft] = useState<string | null>(null);
  const [emailDraftLoading, setEmailDraftLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const [voiceConfigured, setVoiceConfigured] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pendingVoiceResultRef = useRef<AssistantChatResponse | null>(null);
  const chatLogRef = useRef<ChatEntry[]>([]);
  chatLogRef.current = chatLog;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatLog, loading]);

  useEffect(() => {
    let cancelled = false;
    checkHealth()
      .then((health) => {
        if (!cancelled) setVoiceConfigured(health.voice_configured);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  function historyFor(log: ChatEntry[]): HistoryTurn[] {
    return log.filter((e) => e.text).slice(-8).map((e) => ({ role: e.role, text: e.text }));
  }

  function lastUserText(log: ChatEntry[]): string | null {
    for (let i = log.length - 1; i >= 0; i--) if (log[i].role === "user") return log[i].text;
    return null;
  }

  const voice = useGafVoice({
    onTranscript: (role, text) => {
      if (role === "user") {
        setChatLog((log) => [...log, { role: "user", text, voice: true }]);
        return;
      }
      const pending = pendingVoiceResultRef.current;
      pendingVoiceResultRef.current = null;
      setChatLog((log) => [...log, { ...(pending ? entryFromResponse(pending) : { role: "assistant" as const }), role: "assistant", text, voice: true, details: pending?.order_details }]);
    },
    onToolResult: (result) => {
      pendingVoiceResultRef.current = result;
      setTimeline(result.agent_timeline);
    },
  });

  const voiceOn = voice.state === "on" || voice.state === "connecting";

  useEffect(() => {
    onCallStateChange(voiceOn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voiceOn]);

  useEffect(() => {
    if (!active) voice.stopVoice();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // Sidebar phone button: toggle the live call.
  const lastCallRequest = useRef(0);
  useEffect(() => {
    if (callRequest === 0 || callRequest === lastCallRequest.current) return;
    lastCallRequest.current = callRequest;
    if (voiceOn) voice.stopVoice();
    else void voice.startVoice();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [callRequest]);

  // Demo scenario picked from the header menu: prefill the composer.
  useEffect(() => {
    if (!pendingPrompt) return;
    setMessage(pendingPrompt.text);
    textareaRef.current?.focus();
  }, [pendingPrompt]);

  // Emails sent from the inbox window: run each through the Coordinator.
  const lastEmailNonce = useRef(0);
  useEffect(() => {
    if (!emailRequest || emailRequest.nonce === lastEmailNonce.current) return;
    lastEmailNonce.current = emailRequest.nonce;
    void runEmails(emailRequest.ids);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emailRequest]);

  async function runEmails(ids: string[]) {
    setLoading(true);
    setLoadingLabel(`Reading ${ids.length} email${ids.length === 1 ? "" : "s"} and preparing each request…`);
    setError(null);
    const startedAt = performance.now();
    try {
      const items = await emailIntake(ids, historyFor(chatLogRef.current));
      const latencyMs = (performance.now() - startedAt) / Math.max(1, items.length);
      const additions: ChatEntry[] = [];
      for (const item of items) {
        if (item.status !== "processed" || !item.result) {
          additions.push({ role: "assistant", text: `Email ${item.email_id} could not be processed.`, routedTo: "chat", status: "error" });
          continue;
        }
        additions.push({
          role: "user",
          text: item.request || "",
          fromEmail: { fromName: item.email?.fromName || "Customer", subject: item.email?.subject || "", emailId: item.email_id },
        });
        additions.push(entryFromResponse(item.result, latencyMs));
        setTimeline(item.result.agent_timeline);
        if (item.result.handoff_suggested) setHandoff(true);
      }
      setChatLog((log) => [...log, ...additions]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not process the emails.");
    } finally {
      setLoading(false);
      setLoadingLabel(null);
      onEmailsProcessed(ids);
    }
  }

  async function submit(text: string) {
    if (!text.trim() || loading) return;
    setMessage("");
    setLoading(true);
    setLoadingLabel(null);
    setError(null);
    const history = historyFor(chatLog);
    setChatLog((log) => [...log, { role: "user", text }]);
    const startedAt = performance.now();
    try {
      const response = await assistantChat(text, undefined, history);
      const latencyMs = performance.now() - startedAt;
      setTimeline(response.agent_timeline);
      setHandoff(response.handoff_suggested);
      setChatLog((log) => [...log, entryFromResponse(response, latencyMs)]);
      if (response.routed_to === "warranty") onActivity();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRecheck(idx: number, fields: OrderRecheckFields) {
    setRecheckingIdx(idx);
    setError(null);
    const history = historyFor(chatLog.slice(0, idx));
    try {
      const response = await recheckOrder(fields, history);
      setTimeline(response.agent_timeline);
      setChatLog((log) =>
        log.map((entry, i) =>
          i === idx
            ? { ...entry, text: response.agent_message || entry.text, status: response.status, sessionId: response.order_session_id, details: response.order_details, guardrails: response.guardrails, products: response.products, clarification: response.clarification }
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
      submit(message);
    }
  }

  async function handleConfirm(sessionId: string, duplicateAcknowledged: boolean) {
    setConfirmingSessionId(sessionId);
    try {
      const response = await confirmOrder(sessionId, duplicateAcknowledged);
      if (response.status === "confirmed") {
        setConfirmedSessions((prev) => ({ ...prev, [sessionId]: response }));
        onActivity();
      } else {
        setError(response.message || "Could not confirm order.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm order.");
    } finally {
      setConfirmingSessionId(null);
    }
  }

  async function handleDraftEmail() {
    setEmailDraftLoading(true);
    setCopied(false);
    setEmailSent(false);
    try {
      const result = await draftEmail(historyFor(chatLog), rep?.repId);
      setEmailDraft(result.recap);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not draft the email.");
    } finally {
      setEmailDraftLoading(false);
    }
  }

  async function copyDraft() {
    if (!emailDraft) return;
    try {
      await navigator.clipboard.writeText(emailDraft);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const hasConversation = chatLog.some((e) => e.role === "assistant");
  const lastAssistantIdx = (() => {
    for (let i = chatLog.length - 1; i >= 0; i--) if (chatLog[i].role === "assistant") return i;
    return -1;
  })();
  const voiceEntries = chatLog.filter((e) => e.voice).slice(-4);

  return (
    <div className="workspace">
      <section className="panel chat-shell" aria-label="Assistant conversation">
        <div className="chat-shell-header">
          <span className="status-dot" />
          <span className="name">Assistant</span>
          <span className="role">· orders, pricing, warranty, contractors -- routed to the right specialist each turn</span>
          <span className="spacer" />
          {rep && <span className="rep-context" title="Orders are credited to each account's own rep">Signed in as {rep.name}</span>}
        </div>

        <div className="chat-messages">
          {chatLog.length === 0 && (
            <div className="chat-empty-state">
              <div className="empty-icon">
                <SparkIcon size={22} />
              </div>
              <p>
                Type what the customer needs -- a full order, a bulk list, a house description, a warranty question, or "find certified roofers near 30061". Pull emails in from the inbox on the left, start a live call, or pick a demo scenario from the menu above.
              </p>
            </div>
          )}

          {chatLog.map((entry, idx) => {
            const isLast = idx === lastAssistantIdx;
            const quickReplies = isLast && entry.clarification?.quick_replies?.length ? entry.clarification.quick_replies : [];
            return (
              <div key={idx} className={`chat-bubble-row ${entry.role} ${hasOrderForm(entry) ? "has-form" : ""}`}>
                {entry.role === "user" && entry.fromEmail && (
                  <div className="bubble-meta email-meta">
                    <MailIcon size={13} />
                    <span>From email · {entry.fromEmail.fromName} · "{entry.fromEmail.subject}"</span>
                  </div>
                )}
                {entry.role === "assistant" && (routeLabel(entry.routedTo) || (!hasOrderForm(entry) && statusBadge(entry))) && (
                  <div className="bubble-meta">
                    {routeLabel(entry.routedTo) && <span>{routeLabel(entry.routedTo)}</span>}
                    {!hasOrderForm(entry) && statusBadge(entry)}
                  </div>
                )}
                <div className={bubbleClass(entry)}>
                  {entry.voice && <span className="voice-mark">{entry.role === "user" ? <MicIcon size={14} /> : <SpeakerIcon size={14} />}</span>}
                  {hasOrderForm(entry) ? (
                    <OrderForm
                      details={entry.details!}
                      status={entry.status as "ready_for_review" | "blocked"}
                      sessionId={entry.sessionId}
                      rechecking={recheckingIdx === idx}
                      confirming={!!entry.sessionId && confirmingSessionId === entry.sessionId}
                      confirmed={!!(entry.sessionId && confirmedSessions[entry.sessionId])}
                      confirmMessage={entry.sessionId ? confirmedSessions[entry.sessionId]?.message : null}
                      onRecheck={(fields) => handleRecheck(idx, fields)}
                      onConfirm={(duplicateAcknowledged) => entry.sessionId && handleConfirm(entry.sessionId, duplicateAcknowledged)}
                    />
                  ) : entry.role === "assistant" && entry.routedTo === "order" && !entry.voice && entry.status !== "needs_clarification" ? (
                    <OrderSummary text={entry.text} />
                  ) : (
                    <span className="bubble-text">
                      {entry.status === "needs_review" && <span className="review-flag">Draft -- pending human review. </span>}
                      {entry.text}
                    </span>
                  )}
                  {entry.estimate?.status === "ok" && <EstimateCard estimate={entry.estimate} />}
                </div>

                {entry.role === "assistant" && entry.confidence != null && (entry.status === "answered" || entry.status === "needs_review") && (
                  <ConfidenceMeter confidence={entry.confidence} review={entry.review} />
                )}
                {entry.role === "assistant" && entry.products && entry.products.length > 0 && <ProductCardRow products={entry.products} />}
                {entry.role === "assistant" && entry.contractors && entry.contractors.length > 0 && <ContractorList contractors={entry.contractors} location={entry.location} />}
                {quickReplies.length > 0 && (
                  <div className="quick-replies" aria-label="Suggested replies">
                    {quickReplies.map((reply) => (
                      <button key={reply} className="chip" onClick={() => submit(reply)} disabled={loading}>
                        {reply}
                      </button>
                    ))}
                  </div>
                )}
                {entry.role === "assistant" && <GuardrailsCard items={entry.guardrails} />}
                {entry.role === "assistant" && (
                  <div className="bubble-footer">
                    {entry.latencyMs !== undefined && <span className="latency-badge">{(entry.latencyMs / 1000).toFixed(1)}s</span>}
                    <FeedbackButtons context={{ route: entry.routedTo ?? null, status: entry.status ?? null, user_message: lastUserText(chatLog.slice(0, idx)), assistant_message: entry.text }} />
                  </div>
                )}
                {entry.role === "assistant" && entry.status === "ready_for_review" && entry.sessionId && !hasOrderForm(entry) && (
                  <div className="action-row">
                    {confirmedSessions[entry.sessionId] ? (
                      <div className="confirmed-banner">
                        <CheckIcon size={14} strokeWidth={3} />
                        {confirmedSessions[entry.sessionId].message}
                      </div>
                    ) : (
                      <button className="primary-button" onClick={() => handleConfirm(entry.sessionId!, true)} disabled={confirmingSessionId === entry.sessionId}>
                        {confirmingSessionId === entry.sessionId ? "Confirming…" : "Confirm order"}
                      </button>
                    )}
                  </div>
                )}
                {entry.role === "assistant" && (entry.sources?.length ?? 0) > 0 && (
                  <div className="bubble-sources">
                    {entry.sources!.map((source) => (
                      <SourceCard key={source.document_id} source={source} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}

          {loading && (
            <div className="chat-bubble-row assistant">
              <div className="chat-bubble assistant">
                {loadingLabel ? (
                  <span className="bubble-text" style={{ color: "var(--text-muted)" }}>{loadingLabel}</span>
                ) : (
                  <span className="thinking" aria-label="Thinking"><span /><span /><span /></span>
                )}
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="composer-wrap">
          {error && <div className="error-banner" style={{ marginBottom: 10 }}>{error}</div>}
          {voice.state === "error" && <div className="error-banner" style={{ marginBottom: 10 }}>Voice: {voice.hint}</div>}
          {handoff && (
            <div className="handoff-banner" role="status">
              <UserIcon size={16} />
              <span className="grow">This customer sounds like they may want a person -- consider looping in your sales manager.</span>
              <button className="chip" onClick={() => setHandoff(false)}>Got it</button>
            </div>
          )}
          {voiceOn ? (
            <div className="voice-bar">
              <span className={`pill ${voice.state === "on" ? "on" : "busy"}`}>{voice.state === "on" ? "Live call" : "Connecting"}</span>
              <span className="vhint">{voice.hint}</span>
              <button className="icon-button danger" onClick={voice.stopVoice} aria-label="End call">
                <StopIcon size={16} />
              </button>
            </div>
          ) : (
            <div className="chat-input-bar">
              <textarea ref={textareaRef} rows={1} value={message} onChange={(e) => setMessage(e.target.value)} onKeyDown={handleKeyDown} placeholder="What does the customer need?" aria-label="Message" />
              <button className="icon-button ghost" onClick={voice.startVoice} disabled={!voiceConfigured} aria-label="Start live call" title={voiceConfigured ? "Start a live call" : "Voice isn't set up in this environment yet"}>
                <MicIcon />
              </button>
              <button className="icon-button primary" onClick={() => submit(message)} disabled={loading || !message.trim()} aria-label="Send">
                <SendIcon size={17} />
              </button>
            </div>
          )}
        </div>
      </section>

      <div className="side-stack">
        <SidePanel title="Agent activity">
          {timeline.length > 0 ? <AgentTimeline steps={timeline} /> : <div className="panel-hint">Each step the agents take for the latest message shows up here.</div>}
        </SidePanel>

        <SidePanel title="Customer email">
          <div className="recap-actions">
            <button className="primary-button" onClick={handleDraftEmail} disabled={!hasConversation || emailDraftLoading}>
              <MailIcon size={15} />
              {emailDraftLoading ? "Drafting…" : emailDraft ? "Redraft" : "Draft email"}
            </button>
            {emailDraft && (
              <button className="chip subtle" onClick={copyDraft}>
                <CopyIcon size={13} />
                {copied ? "Copied" : "Copy"}
              </button>
            )}
            {emailDraft && !emailSent && (
              <button className="chip subtle" onClick={() => setEmailSent(true)}>
                <SendIcon size={13} />
                Send
              </button>
            )}
          </div>
          {emailSent && (
            <div className="confirmed-banner" style={{ marginTop: 10 }}>
              <CheckIcon size={14} strokeWidth={3} />
              Marked as sent (demo -- no mail service connected)
            </div>
          )}
          {emailDraft ? (
            <textarea className="recap-text" readOnly value={emailDraft} aria-label="Customer email draft" />
          ) : (
            <div className="panel-hint" style={{ marginTop: 10 }}>Drafts a professional follow-up email to the customer from this conversation only -- nothing added that wasn't said. Signed as {rep?.name ?? "the rep"}.</div>
          )}
        </SidePanel>
      </div>

      {voiceOn && (
        <div className="call-window" role="dialog" aria-label="Live call">
          <div className="call-window-head">
            <PhoneIcon size={16} />
            <span className="grow">{voice.state === "on" ? "Live call -- transcribing" : "Connecting…"}</span>
            <button className="icon-button danger small" onClick={voice.stopVoice} aria-label="End call" title="End call">
              <StopIcon size={14} />
            </button>
          </div>
          <canvas className="mic-meter" ref={voice.meterCanvasRef} />
          <div className="call-transcript">
            {voiceEntries.length === 0 ? <span className="muted">{voice.hint || "Say what the customer needs…"}</span> : voiceEntries.map((e, i) => (
              <div key={i} className={`call-line ${e.role}`}>
                <span className="who">{e.role === "user" ? "You" : "Assistant"}</span>
                <span>{e.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
