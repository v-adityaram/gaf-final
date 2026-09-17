import { useEffect, useMemo, useState } from "react";
import type { InboxEmail } from "../types";
import { shortDate } from "../lib/format";
import { useDismiss } from "../lib/dismiss";
import { InboxIcon, XIcon } from "./Icons";

interface EmailWindowProps {
  open: boolean;
  onClose: () => void;
  emails: InboxEmail[];
  loading: boolean;
  sending: boolean;
  processedIds: string[];
  onSend: (ids: string[]) => void;
  repName?: string | null;
}

export default function EmailWindow({ open, onClose, emails, loading, sending, processedIds, onSend, repName }: EmailWindowProps) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [focusedId, setFocusedId] = useState<string | null>(null);

  useDismiss(open, onClose);

  const processed = useMemo(() => new Set(processedIds), [processedIds]);
  const selectable = useMemo(() => emails.filter((e) => !processed.has(e.emailId)), [emails, processed]);
  const unread = emails.filter((e) => !e.read && !processed.has(e.emailId)).length;

  // Drop any selection that has since been processed, and default the
  // reading pane to the first email once the list arrives.
  useEffect(() => {
    setSelected((prev) => {
      const next = new Set([...prev].filter((id) => !processed.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [processed]);

  useEffect(() => {
    if (focusedId === null && emails.length > 0) setFocusedId(emails[0].emailId);
  }, [emails, focusedId]);

  if (!open) return null;

  const focused = emails.find((e) => e.emailId === focusedId) ?? null;
  const count = selected.size;

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <section className="email-window" role="dialog" aria-modal="false" aria-label="Inbox">
      <header className="email-titlebar">
        <InboxIcon size={16} className="email-title-icon" />
        <span className="email-title">
          Inbox{repName ? <span className="email-title-rep"> &middot; {repName}</span> : null}
        </span>
        {unread > 0 && <span className="status-badge amber">{unread} unread</span>}
        <span className="spacer" />
        <button type="button" className="icon-button ghost email-close" onClick={onClose} aria-label="Close inbox">
          <XIcon size={16} />
        </button>
      </header>

      <div className="email-body">
        <ul className="email-list" aria-label="Messages">
          {loading && emails.length === 0 && <li className="email-empty">Loading inbox&hellip;</li>}
          {!loading && emails.length === 0 && <li className="email-empty">No messages.</li>}
          {emails.map((e) => {
            const done = processed.has(e.emailId);
            const checked = selected.has(e.emailId);
            const isFocused = e.emailId === focusedId;
            return (
              <li
                key={e.emailId}
                className={`email-row${isFocused ? " focused" : ""}${done ? " processed" : ""}${e.read ? "" : " unread"}`}
                onClick={() => setFocusedId(e.emailId)}
              >
                <input
                  type="checkbox"
                  className="email-check"
                  checked={checked && !done}
                  disabled={done || sending}
                  onChange={() => toggle(e.emailId)}
                  onClick={(ev) => ev.stopPropagation()}
                  aria-label={`Select email from ${e.fromName}: ${e.subject}`}
                />
                <button
                  type="button"
                  className="email-row-main"
                  onClick={() => setFocusedId(e.emailId)}
                  aria-pressed={isFocused}
                  aria-label={`Open email from ${e.fromName}: ${e.subject}`}
                >
                  <span className="email-row-top">
                    <span className="email-from">{e.fromName}</span>
                    <span className="email-time">{shortDate(e.receivedAt)}</span>
                  </span>
                  <span className="email-subject">{e.subject}</span>
                  <span className="email-tags">
                    {e.category && <span className={`email-tag cat-${e.category}`}>{e.category}</span>}
                    {done && <span className="status-badge green">Sent to assistant</span>}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        <div className="email-reading" aria-live="polite">
          {focused ? (
            <>
              <div className="email-reading-head">
                <div className="email-reading-subject">{focused.subject}</div>
                <div className="email-reading-meta">
                  <span className="email-from">{focused.fromName}</span> &lt;{focused.fromEmail}&gt;
                  <span className="dot-sep" aria-hidden="true">
                    &middot;
                  </span>
                  {shortDate(focused.receivedAt)}
                </div>
                <div className="email-reading-meta">
                  {focused.customerName}
                  {focused.tradeName ? ` (${focused.tradeName})` : ""}
                </div>
              </div>
              <pre className="email-reading-body">{focused.body}</pre>
            </>
          ) : (
            <div className="email-empty">Select a message to read it.</div>
          )}
        </div>
      </div>

      <footer className="email-footer">
        <button
          type="button"
          className="chip"
          onClick={() => setSelected(new Set(selectable.map((e) => e.emailId)))}
          disabled={selectable.length === 0 || sending}
        >
          Select all
        </button>
        <button type="button" className="chip" onClick={() => setSelected(new Set())} disabled={count === 0 || sending}>
          Clear
        </button>
        <span className="spacer" />
        <button type="button" className="primary-button" onClick={() => onSend([...selected])} disabled={count === 0 || sending}>
          {sending ? "Sending…" : `Send ${count} to assistant`}
        </button>
      </footer>
    </section>
  );
}
