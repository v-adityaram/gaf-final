import { useCallback, useRef, useState } from "react";
import type { RepDashboard, SalesRep } from "../types";
import { money, percent } from "../lib/format";
import { useDismiss } from "../lib/dismiss";
import { ChevronIcon } from "./Icons";

interface RepBadgeProps {
  reps: SalesRep[];
  currentRepId: string | null;
  dashboard: RepDashboard | null;
  loading: boolean;
  onSelectRep: (repId: string) => void;
}

const MAX_ORDERS = 8;

// Explicit map so a credit status never falls through to the generic
// badgeClass() heuristics (which key on order/guardrail words).
function creditBadgeClass(status: string): string {
  const s = status.trim().toUpperCase();
  if (s === "GOOD STANDING" || s === "GOOD") return "status-badge green";
  if (s === "REVIEW" || s === "UNDER REVIEW") return "status-badge amber";
  if (s === "CREDIT HOLD" || s === "HOLD") return "status-badge red";
  return "status-badge";
}

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export default function RepBadge({ reps, currentRepId, dashboard, loading, onSelectRep }: RepBadgeProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, close, rootRef);

  const rep = dashboard?.rep ?? reps.find((r) => r.repId === currentRepId) ?? null;
  const initials = rep ? rep.initials || initialsOf(rep.name) : "--";
  const commission = dashboard?.commission ?? null;
  const quota = commission?.quota_usd ?? rep?.quotaUsd ?? null;
  const progress = commission?.quota_progress ?? (quota && commission ? commission.booked_sales_usd / quota : null);
  const progressPct = progress === null ? 0 : Math.max(0, Math.min(100, Math.round(progress * 100)));
  const orders = dashboard ? dashboard.orders.slice(0, MAX_ORDERS) : [];
  const accountName = (accountId: string) => {
    const acc = dashboard?.accounts.find((a) => a.accountId === accountId);
    return acc ? acc.tradeName || acc.customerName : accountId;
  };

  return (
    <div className="rep-badge-root" ref={rootRef}>
      <button
        type="button"
        className={`rep-chip${open ? " open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={rep ? `Sales rep ${rep.name}, ${rep.territory}. Open rep dashboard` : "Open rep dashboard"}
      >
        <span className="rep-avatar" aria-hidden="true">
          {initials}
        </span>
        <span className="rep-chip-text">
          <span className="rep-name">{rep?.name ?? "Select rep"}</span>
          {rep && <span className="rep-territory">{rep.territory}</span>}
        </span>
        <ChevronIcon size={14} className={`chev${open ? " up" : ""}`} />
      </button>

      {open && (
        <div className="rep-popover" role="dialog" aria-label="Rep dashboard">
          <label className="rep-select">
            <span>Signed in as</span>
            <select value={currentRepId ?? ""} onChange={(e) => onSelectRep(e.target.value)} aria-label="Switch sales rep">
              {currentRepId === null && <option value="">Choose a rep</option>}
              {reps.map((r) => (
                <option key={r.repId} value={r.repId}>
                  {r.name} &mdash; {r.territory}
                </option>
              ))}
            </select>
          </label>

          {loading && !dashboard ? (
            <div className="rep-skeleton" aria-busy="true">
              <div className="rep-stat-grid">
                {Array.from({ length: 4 }, (_, i) => (
                  <div key={i} className="rep-stat skeleton" />
                ))}
              </div>
              <div className="rep-loading">Loading&hellip;</div>
            </div>
          ) : dashboard && commission ? (
            <>
              <div className="rep-stat-grid">
                <div className="rep-stat">
                  <span>Booked sales</span>
                  <strong>{money(commission.booked_sales_usd)}</strong>
                </div>
                <div className="rep-stat">
                  <span>Commission</span>
                  <strong>{money(commission.booked_commission_usd)}</strong>
                  <small>{percent(commission.rate, 1)} rate</small>
                </div>
                <div className="rep-stat">
                  <span>This session</span>
                  <strong>{money(commission.session_commission_usd)}</strong>
                  <small>from {money(commission.session_sales_usd)}</small>
                </div>
                <div className="rep-stat">
                  <span>Pipeline</span>
                  <strong>{money(commission.pipeline_usd)}</strong>
                </div>
              </div>

              {quota !== null && (
                <div className="rep-quota">
                  <div className="rep-quota-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressPct} aria-label="Quota progress">
                    <div className="rep-quota-fill" style={{ width: `${progressPct}%` }} />
                  </div>
                  <div className="rep-quota-label">
                    {money(commission.booked_sales_usd)} of {money(quota)} quota ({progressPct}%)
                  </div>
                </div>
              )}

              <section className="rep-section">
                <h4>Accounts</h4>
                {dashboard.accounts.length === 0 ? (
                  <p className="panel-hint">No accounts assigned.</p>
                ) : (
                  <ul className="rep-accounts">
                    {dashboard.accounts.map((a) => (
                      <li key={a.accountId}>
                        <span className="rep-account-name">
                          {a.tradeName || a.customerName}
                          <span className="rep-account-city">
                            {a.city}, {a.state}
                          </span>
                        </span>
                        <span className={creditBadgeClass(a.creditStatus)}>{a.creditStatus}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="rep-section">
                <h4>Recent orders</h4>
                {orders.length === 0 ? (
                  <p className="panel-hint">No orders on file.</p>
                ) : (
                  <div className="rep-table-wrap">
                    <table className="rep-orders">
                      <thead>
                        <tr>
                          <th scope="col">Order</th>
                          <th scope="col">Account</th>
                          <th scope="col" className="num">
                            Total
                          </th>
                          <th scope="col">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {orders.map((o) => (
                          <tr key={o.orderId}>
                            <td className="mono">{o.orderId}</td>
                            <td>{accountName(o.accountId)}</td>
                            <td className="num">{money(o.totalUsd)}</td>
                            <td>{o.status ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="rep-section">
                <h4>Confirmed this session</h4>
                {dashboard.confirmed_this_session.length === 0 ? (
                  <p className="panel-hint">No orders confirmed yet this session.</p>
                ) : (
                  <ul className="rep-confirmed">
                    {dashboard.confirmed_this_session.map((c) => (
                      <li key={c.confirmation_id}>
                        <span className="rep-account-name">{c.trade_name || c.customer_name || c.customer_id || "Customer"}</span>
                        <span className="rep-confirmed-amounts">
                          <strong>{money(c.order_total)}</strong>
                          <small>{money(c.commission_amount)} comm.</small>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          ) : (
            <p className="panel-hint">Pick a rep to load their dashboard.</p>
          )}
        </div>
      )}
    </div>
  );
}
