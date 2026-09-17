import { useEffect, useState } from "react";
import { getConfirmedOrders, getMetricsOrders, getMetricsRequests, getMetricsSummary, getReviews, resolveReview } from "../api";
import ConfidenceMeter from "../components/ConfidenceMeter";
import GuardrailsCard from "../components/GuardrailsCard";
import { badgeClass } from "../lib/badge";
import { money } from "../lib/format";
import type { ConfirmedOrderRecord, MetricsRequestRecord, MetricsSummary, OrderHistoryRecord, ReviewItem } from "../types";

const FILTERS: Array<{ value: string; label: string }> = [
  { value: "All", label: "All" },
  { value: "READY FOR HUMAN REVIEW", label: "Ready" },
  { value: "CONFIRMED", label: "Confirmed" },
  { value: "BLOCKED", label: "Blocked" },
  { value: "WARNING", label: "Warning" },
];

function fmtMs(value: number | null | undefined): string {
  return value == null ? "N/A" : `${(value / 1000).toFixed(2)}s`;
}

function fmt(value: unknown): string {
  if (value === null || value === undefined || value === "") return "N/A";
  return String(value);
}

function fmtTokens(value: number | null | undefined): string {
  return value == null ? "N/A" : value.toLocaleString();
}

function time(value: string | null | undefined): string {
  if (!value) return "N/A";
  return new Date(value).toLocaleString();
}

function truncate(text: string, max = 140): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function SummaryCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RequestCard({ request }: { request: MetricsRequestRecord }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="request-card">
      <div className="request-card-head">
        <span className="request-type-tag">{request.request_type}</span>
        <span className={badgeClass(request.status)}>{request.status}</span>
      </div>
      <p className="request-text">&ldquo;{truncate(request.user_request)}&rdquo;</p>
      <div className="request-meta-row">
        <span>Model: {request.model_name || "N/A"}</span>
        <span>Latency: {fmtMs(request.total_latency_ms)}</span>
        <span>Tokens: {fmtTokens(request.total_tokens)}</span>
      </div>
      <GuardrailsCard items={request.guardrails} />
      <button className="chip subtle request-details-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "Hide details" : "View details"}
      </button>
      {open && (
        <dl className="request-card-details">
          <div><dt>Timestamp</dt><dd>{time(request.timestamp)}</dd></div>
          <div><dt>Input tokens</dt><dd>{fmt(request.input_tokens)}</dd></div>
          <div><dt>Output tokens</dt><dd>{fmt(request.output_tokens)}</dd></div>
          <div><dt>Total tokens</dt><dd>{fmtTokens(request.total_tokens)}</dd></div>
          <div><dt>Total latency</dt><dd>{request.total_latency_ms != null ? `${request.total_latency_ms.toFixed(2)} ms` : "N/A"}</dd></div>
        </dl>
      )}
    </div>
  );
}

function ReviewCard({ review, onResolved }: { review: ReviewItem; onResolved: () => void }) {
  const [answer, setAnswer] = useState(review.draft_answer ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function act(decision: "approve" | "edit" | "reject") {
    setBusy(true);
    setErr(null);
    try {
      await resolveReview(review.review_id, decision, decision === "reject" ? null : answer, "Sales manager");
      onResolved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not resolve review.");
    } finally {
      setBusy(false);
    }
  }
  const edited = answer !== (review.draft_answer ?? "");
  return (
    <div className="review-card">
      <div className="review-card-head">
        <span className="request-type-tag">{review.review_id}</span>
        <span className={badgeClass(review.status === "pending" ? "WARNING" : "PASSED")}>{review.status === "pending" ? "Pending" : `Resolved · ${review.decision}`}</span>
        <span className="muted">{time(review.created_at)}</span>
      </div>
      <p className="request-text">&ldquo;{review.question}&rdquo;</p>
      <ConfidenceMeter confidence={review.confidence} review={{ required: true, kind: "human_review", reasons: review.reasons, review_id: review.review_id, threshold: 95 }} />
      {review.status === "pending" ? (
        <>
          <textarea className="recap-text review-answer" value={answer} onChange={(e) => setAnswer(e.target.value)} aria-label="Draft answer" />
          {err && <div className="error-banner">{err}</div>}
          <div className="filter-row">
            <button className="primary-button" disabled={busy} onClick={() => act(edited ? "edit" : "approve")}>{busy ? "Saving…" : edited ? "Approve with edits" : "Approve"}</button>
            <button className="chip" disabled={busy} onClick={() => act("reject")}>Reject</button>
            {review.sources.length > 0 && <span className="muted">Sources: {review.sources.map((s) => s.document_id).join(", ")}</span>}
          </div>
        </>
      ) : (
        <p className="request-text muted">{review.final_answer}</p>
      )}
    </div>
  );
}

interface MetricsPageProps {
  // The page stays mounted permanently (see App.tsx) so its filter
  // selection survives switching tabs -- this just tells it when it has
  // become visible again, so it can pull fresh numbers rather than
  // showing whatever it last loaded, possibly turns ago.
  active: boolean;
  repId?: string | null;
  onReviewsChanged?: () => void;
}

export default function MetricsPage({ active, repId, onReviewsChanged }: MetricsPageProps) {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [requests, setRequests] = useState<MetricsRequestRecord[]>([]);
  const [orders, setOrders] = useState<OrderHistoryRecord[]>([]);
  const [confirmed, setConfirmed] = useState<ConfirmedOrderRecord[]>([]);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [reviewFilter, setReviewFilter] = useState<"pending" | "all">("pending");
  const [filter, setFilter] = useState<string>("All");
  const [error, setError] = useState<string | null>(null);
  const [visibleRequests, setVisibleRequests] = useState(10);

  async function loadReviews(which: "pending" | "all" = reviewFilter) {
    try {
      const r = await getReviews(which === "pending" ? "pending" : undefined);
      setReviews(r.reviews);
      onReviewsChanged?.();
    } catch {
      setReviews([]);
    }
  }

  async function load(selected = filter) {
    try {
      setError(null);
      const [summaryData, requestData, orderData, confirmedData] = await Promise.all([
        getMetricsSummary(),
        getMetricsRequests(100),
        getMetricsOrders(selected, 100),
        getConfirmedOrders(50),
      ]);
      setSummary(summaryData);
      setRequests(requestData);
      setOrders(orderData);
      setConfirmed(confirmedData);
      void loadReviews();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load metrics.");
    }
  }

  useEffect(() => {
    if (active) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, repId]);

  const pendingCount = reviews.filter((r) => r.status === "pending").length;
  const sessionSales = confirmed.reduce((sum, o) => sum + (o.order_total ?? 0), 0);
  const sessionCommission = confirmed.reduce((sum, o) => sum + (o.commission_amount ?? 0), 0);

  return (
    <div className="metrics-page">
      {error && <div className="error-banner">{error}</div>}

      <section className="metrics-section">
        <div className="section-title-row">
          <h2>Human review queue {pendingCount > 0 && <span className="status-badge amber">{pendingCount} pending</span>}</h2>
          <div className="filter-row">
            <button className="chip subtle" onClick={() => void loadReviews()}>Refresh</button>
            <button className={`chip ${reviewFilter === "pending" ? "active-filter" : ""}`} onClick={() => { setReviewFilter("pending"); void loadReviews("pending"); }}>Pending</button>
            <button className={`chip ${reviewFilter === "all" ? "active-filter" : ""}`} onClick={() => { setReviewFilter("all"); void loadReviews("all"); }}>All</button>
          </div>
        </div>
        <p className="panel-hint">Warranty answers below 95% confidence land here as drafts. Approve, edit or reject -- nothing goes to the customer until a human signs off.</p>
        <div className="request-card-list">
          {reviews.map((review) => (
            <ReviewCard key={`${review.review_id}-${review.status}`} review={review} onResolved={() => void loadReviews()} />
          ))}
          {reviews.length === 0 && <div className="panel-hint">Nothing waiting for review.</div>}
        </div>
      </section>

      <section className="metrics-section">
        <div className="section-title-row">
          <h2>Confirmed this session</h2>
          <span className="muted">{confirmed.length} order{confirmed.length === 1 ? "" : "s"} · {money(sessionSales)} · commission {money(sessionCommission)}</span>
        </div>
        <div className="table-wrap">
          <table className="metrics-table">
            <thead>
              <tr><th>Confirmed</th><th>Customer</th><th>Lines</th><th>Squares</th><th>Discounts</th><th>Total</th><th>Commission</th><th>Rep</th></tr>
            </thead>
            <tbody>
              {confirmed.map((o) => (
                <tr key={o.confirmation_id}>
                  <td>{time(o.confirmed_at)}</td>
                  <td>{fmt(o.trade_name || o.customer_name)}<br /><span className="muted">{fmt(o.customer_id)}</span></td>
                  <td>{o.lines?.length ?? 1}<br /><span className="muted">{fmt(o.product)}{o.color ? ` · ${o.color}` : ""}</span></td>
                  <td>{fmt(o.total_squares)}</td>
                  <td>{o.discounts && o.discounts.length ? o.discounts.join(", ") : "—"}</td>
                  <td>{money(o.order_total)}</td>
                  <td>{money(o.commission_amount)}</td>
                  <td className="muted">{fmt(o.sales_rep_id)}</td>
                </tr>
              ))}
              {confirmed.length === 0 && <tr><td colSpan={8}>No orders confirmed yet this session.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="metrics-grid" aria-label="AI performance summary">
        <SummaryCard label="Average Latency" value={fmtMs(summary?.average_latency_ms)} />
        <SummaryCard label="Active Model" value={summary?.active_model || "N/A"} />
        <SummaryCard label="Total Requests" value={summary?.total_requests ?? 0} />
        <SummaryCard label="Confirmed Orders" value={summary?.confirmed_orders ?? 0} />
        <SummaryCard label="Blocked Orders" value={summary?.blocked_orders ?? 0} />
      </section>

      <section className="metrics-section">
        <div className="section-title-row">
          <h2>AI Request History</h2>
          <button className="chip subtle" onClick={() => void load()}>Refresh</button>
        </div>
        <div className="request-card-list">
          {requests.slice(0, visibleRequests).map((request) => (
            <RequestCard key={request.request_id} request={request} />
          ))}
          {requests.length === 0 && <div className="panel-hint">No AI request history yet.</div>}
          {requests.length > visibleRequests && (
            <button className="chip subtle" onClick={() => setVisibleRequests((n) => n + 10)}>
              Show 10 more ({requests.length - visibleRequests} remaining)
            </button>
          )}
        </div>
      </section>

      <section className="metrics-section">
        <div className="section-title-row">
          <h2>Order History</h2>
          <div className="filter-row">
            <button className="chip subtle" onClick={() => void load()}>Refresh</button>
            {FILTERS.map((item) => (
              <button
                key={item.value}
                className={`chip ${filter === item.value ? "active-filter" : ""}`}
                onClick={() => {
                  setFilter(item.value);
                  void load(item.value);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <div className="table-wrap">
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Order / Session ID</th>
                <th>Time</th>
                <th>Customer</th>
                <th>Product</th>
                <th>Quantity</th>
                <th>Total</th>
                <th>Status</th>
                <th>Checks</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={`${order.order_session_id}-${order.timestamp}`}>
                  <td className="muted" title={order.order_session_id || undefined}>
                    {order.order_session_id ? order.order_session_id.slice(0, 8) : "N/A"}
                  </td>
                  <td>
                    {time(order.timestamp)}
                    {order.final_status === "CONFIRMED" && order.confirmation_time && (
                      <><br /><span className="muted">Confirmed {time(order.confirmation_time)}</span></>
                    )}
                  </td>
                  <td>{fmt(order.customer_name)}<br /><span className="muted">{fmt(order.customer_id)}</span></td>
                  <td>{fmt(order.product)}<br /><span className="muted">{fmt(order.sku)}</span></td>
                  <td>{fmt(order.quantity)} {fmt(order.unit)}{order.line_count && order.line_count > 1 ? <><br /><span className="muted">{order.line_count} lines</span></> : null}</td>
                  <td>{order.order_total != null ? money(order.order_total) : "N/A"}</td>
                  <td><span className={badgeClass(order.final_status)}>{order.final_status}</span></td>
                  <td>
                    <details className="checks-details">
                      <summary>View Checks</summary>
                      <div className="checks-list">
                        {order.checks.map((check) => (
                          <div className="check-row" key={`${check.name}-${check.status}`}>
                            <span>{check.name}</span>
                            <span className={badgeClass(check.status)}>{check.status}</span>
                            {check.details && (
                              <dl>
                                {Object.entries(check.details).filter(([, value]) => value !== null && value !== undefined && value !== "").map(([key, value]) => (
                                  <div key={key}><dt>{key.replace(/_/g, " ")}</dt><dd>{String(value)}</dd></div>
                                ))}
                              </dl>
                            )}
                          </div>
                        ))}
                      </div>
                    </details>
                  </td>
                </tr>
              ))}
              {orders.length === 0 && <tr><td colSpan={8}>No order history yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
