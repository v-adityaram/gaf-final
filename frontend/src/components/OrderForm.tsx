import { useEffect, useState } from "react";
import type { OrderLineInput, OrderRecheckFields } from "../api";
import { badgeClass } from "../lib/badge";
import { money } from "../lib/format";
import type { OrderDetails, OrderLine } from "../types";
import { CheckIcon, XIcon } from "./Icons";
import PricingTable from "./PricingTable";
import { ShingleSwatch } from "./ProductCard";

const UNIT_OPTIONS = ["squares", "bundles", "rolls", "pieces", "boxes", "packs"];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

interface OrderFormProps {
  details: OrderDetails;
  status: "ready_for_review" | "blocked" | "needs_clarification";
  sessionId?: string | null;
  rechecking: boolean;
  confirming: boolean;
  confirmed: boolean;
  confirmMessage?: string | null;
  onRecheck: (fields: OrderRecheckFields) => void;
  // Duplicate order guard: the backend rejects confirmation of a
  // duplicate-flagged order unless this is explicitly true.
  onConfirm: (duplicateAcknowledged: boolean) => void;
}

interface LineState {
  key: string;
  sku: string;
  product: string;
  colour: string;
  quantity: string;
  unit: string;
  included: boolean;
  source: "customer" | "add_on";
  addOnRule: string | null;
  unitPrice: number;
  priceUnit: string;
  swatch: string | null;
  qualifying: boolean;
  rationale: string | null;
  inventoryNote?: string;
  warnings?: string[];
}

interface FormState {
  customerName: string;
  customerId: string;
  deliveryCity: string;
  deliveryDate: string;
  deliveryMethod: string;
  lines: LineState[];
}

function toLineState(l: OrderLine): LineState {
  return {
    key: `${l.line_no}-${l.sku}`,
    sku: l.sku,
    product: l.product,
    colour: l.colour ?? "",
    quantity: String(l.quantity),
    unit: l.unit,
    included: l.included ?? true,
    source: l.source,
    addOnRule: l.add_on_rule ?? null,
    unitPrice: l.unit_price,
    priceUnit: l.price_unit,
    swatch: l.swatch_hex ?? null,
    qualifying: !!l.qualifying,
    rationale: l.rationale ?? null,
    inventoryNote: l.inventory_note,
    warnings: l.warnings,
  };
}

function toFormState(details: OrderDetails): FormState {
  const deliveryDate = details.delivery_date_resolved || (details.delivery_date && ISO_DATE.test(details.delivery_date) ? details.delivery_date : "");
  const lines = (details.lines ?? []).map(toLineState);
  if (lines.length === 0 && details.sku) {
    lines.push({
      key: `1-${details.sku}`, sku: details.sku, product: details.product ?? "", colour: details.colour ?? "",
      quantity: details.quantity != null ? String(details.quantity) : "", unit: details.unit ?? "squares", included: true,
      source: "customer", addOnRule: null, unitPrice: 0, priceUnit: "", swatch: null, qualifying: false, rationale: null,
    });
  }
  return {
    customerName: details.customer_name ?? "",
    customerId: details.customer_id ?? "",
    deliveryCity: details.delivery_city ?? "",
    deliveryDate,
    deliveryMethod: details.delivery_method ?? "",
    lines,
  };
}

// The AI-extracted order as an editable, multi-line form. Editing a line
// (or ticking an add-on on) and clicking "Recheck Order" reruns unit
// conversion, pricing, discounts and the inventory/credit/duplicate checks
// from scratch on the backend; "Confirm Order" is the human gate.
export default function OrderForm({ details, status, sessionId, rechecking, confirming, confirmed, confirmMessage, onRecheck, onConfirm }: OrderFormProps) {
  const [form, setForm] = useState(() => toFormState(details));
  const [ackDuplicate, setAckDuplicate] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setForm(toFormState(details));
    setAckDuplicate(false);
    setDirty(false);
  }, [details]);

  function setField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setDirty(true);
    setForm((f) => ({ ...f, [key]: value }));
  }

  function setLine(idx: number, patch: Partial<LineState>) {
    setDirty(true);
    setForm((f) => ({ ...f, lines: f.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
  }

  function removeLine(idx: number) {
    setDirty(true);
    setForm((f) => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }));
  }

  function addLine() {
    setDirty(true);
    setForm((f) => ({
      ...f,
      lines: [...f.lines, { key: `new-${Date.now()}`, sku: "", product: "", colour: "", quantity: "", unit: "squares", included: true, source: "customer", addOnRule: null, unitPrice: 0, priceUnit: "", swatch: null, qualifying: false, rationale: null }],
    }));
  }

  function submitRecheck() {
    const lines: OrderLineInput[] = form.lines
      .filter((l) => l.sku || l.product)
      .map((l) => ({
        sku: l.sku || null,
        product: l.product || null,
        colour: l.colour || null,
        quantity: l.quantity.trim() === "" ? null : Number(l.quantity),
        unit: l.unit || null,
        included: l.included,
        source: l.source,
        add_on_rule: l.addOnRule,
      }));
    onRecheck({
      customer_name: form.customerName || null,
      customer_id: form.customerId || null,
      lines,
      include_add_ons: form.lines.some((l) => l.source === "add_on" && l.included),
      delivery_city: form.deliveryCity || null,
      delivery_date: form.deliveryDate || null,
      delivery_method: form.deliveryMethod || null,
    });
  }

  const dateIsIso = ISO_DATE.test(form.deliveryDate);
  const dateWasAutoDetected = !!details.delivery_date_resolved && details.delivery_date !== details.delivery_date_resolved && form.deliveryDate === details.delivery_date_resolved;
  const statusLabel = status === "ready_for_review" ? "READY FOR HUMAN REVIEW" : status === "blocked" ? "BLOCKED" : "NEEDS CLARIFICATION";
  const customerLines = form.lines.filter((l) => l.source === "customer");
  const addOnLines = form.lines.filter((l) => l.source === "add_on");
  const pricing = details.pricing;
  const includedLines = (details.lines ?? []).filter((l) => l.included ?? true);

  function lineRow(l: LineState, idx: number) {
    const i = form.lines.indexOf(l);
    const isAddOn = l.source === "add_on";
    return (
      <div className={`order-line ${isAddOn && !l.included ? "excluded" : ""}`} key={l.key}>
        <div className="order-line-main">
          {isAddOn ? (
            <label className="order-line-include" title={l.rationale ?? undefined}>
              <input type="checkbox" checked={l.included} onChange={(e) => setLine(i, { included: e.target.checked })} aria-label={`Include ${l.product}`} />
            </label>
          ) : (
            <span className="order-line-no">{idx + 1}</span>
          )}
          <ShingleSwatch hex={l.swatch} size={26} />
          <div className="order-line-fields">
            <input value={l.product} onChange={(e) => setLine(i, { product: e.target.value })} placeholder="Product" aria-label="Product" className="grow" />
            <input value={l.colour} onChange={(e) => setLine(i, { colour: e.target.value })} placeholder="Colour" aria-label="Colour" className="colour" />
            <input value={l.sku} onChange={(e) => setLine(i, { sku: e.target.value })} placeholder="SKU" aria-label="SKU" className="mono sku" />
            <input type="number" min="0" step="1" inputMode="numeric" value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} aria-label="Quantity" className="qty" />
            <select value={l.unit} onChange={(e) => setLine(i, { unit: e.target.value })} aria-label="Unit" className="unit">
              {(UNIT_OPTIONS.includes(l.unit) ? UNIT_OPTIONS : [l.unit, ...UNIT_OPTIONS]).map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </div>
          <div className="order-line-price">
            {l.unitPrice > 0 && <span title={`${money(l.unitPrice)} per ${l.priceUnit.toLowerCase()}`}>{money(l.unitPrice)}/{l.priceUnit.toLowerCase()}</span>}
            {l.qualifying && isAddOn && <span className="qualifying-tag" title="Counts toward the four WindProven add-on categories">WindProven</span>}
          </div>
          {!isAddOn && form.lines.length > 1 && (
            <button className="icon-button ghost small" onClick={() => removeLine(i)} aria-label={`Remove ${l.product}`} title="Remove line">
              <XIcon size={14} />
            </button>
          )}
        </div>
        {(l.inventoryNote || (l.warnings && l.warnings.length > 0)) && l.included && (
          <div className={`order-line-note ${l.warnings && l.warnings.length ? "warn" : ""}`}>{l.warnings && l.warnings.length ? l.warnings.join(" ") : l.inventoryNote}</div>
        )}
      </div>
    );
  }

  return (
    <div className="order-form">
      <div className="order-form-grid two">
        <label className="order-form-field">
          <span>Customer</span>
          <input value={form.customerName} onChange={(e) => setField("customerName", e.target.value)} placeholder="Customer name" />
          {details.trade_name && <small className="order-form-hint">{details.trade_name}{details.customer_type ? ` · ${details.customer_type}` : ""}</small>}
        </label>
        <label className="order-form-field">
          <span>Account ID</span>
          <input value={form.customerId} onChange={(e) => setField("customerId", e.target.value)} placeholder="ACC-1001" className="mono" />
          {details.sales_rep_name && <small className="order-form-hint">Rep: {details.sales_rep_name}</small>}
        </label>
      </div>

      <div className="order-lines">
        <div className="order-lines-head">
          <span>Lines</span>
          {details.total_squares != null && details.total_squares > 0 && <span className="muted">{details.total_squares} squares total</span>}
          <button className="chip subtle" onClick={addLine}>+ Add line</button>
        </div>
        {customerLines.map((l, idx) => lineRow(l, idx))}
        {addOnLines.length > 0 && (
          <div className="order-lines-head sub">
            <span>Add-ons</span>
            <span className="muted">{addOnLines.filter((l) => l.included).length} of {addOnLines.length} included -- tick to add, then recheck</span>
          </div>
        )}
        {addOnLines.map((l, idx) => lineRow(l, idx))}
      </div>

      <div className="order-form-grid three">
        <label className="order-form-field">
          <span>Deliver to</span>
          <input value={form.deliveryCity} onChange={(e) => setField("deliveryCity", e.target.value)} placeholder="City" />
        </label>
        <label className="order-form-field">
          <span>Requested date</span>
          <input type="date" value={dateIsIso ? form.deliveryDate : ""} onChange={(e) => setField("deliveryDate", e.target.value)} />
          {dateWasAutoDetected && <small className="order-form-hint order-form-hint-ok">Detected from "{details.delivery_date}"</small>}
          {!dateWasAutoDetected && !dateIsIso && form.deliveryDate && <small className="order-form-hint">Heard: "{form.deliveryDate}" -- pick an exact date</small>}
        </label>
        <label className="order-form-field">
          <span>Delivery method</span>
          <select value={form.deliveryMethod} onChange={(e) => setField("deliveryMethod", e.target.value)}>
            <option value="">Not confirmed</option>
            <option value="job site">Job site</option>
            <option value="warehouse pickup">Warehouse pickup</option>
          </select>
        </label>
      </div>

      {pricing && includedLines.length > 0 && <PricingTable pricing={pricing} lines={includedLines} />}

      <div className="checks-list">
        {details.checks.map((check) => (
          <div className="check-row" key={check.name}>
            <span>{check.name}</span>
            <span className={badgeClass(check.status)}>{check.status}</span>
            {check.details && (
              <dl>
                {Object.entries(check.details)
                  .filter(([, value]) => value !== null && value !== undefined && value !== "" && typeof value !== "object")
                  .map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replace(/_/g, " ")}</dt>
                      <dd>{typeof value === "number" && /total|subtotal|limit|balance|credit/.test(key) && !/percent|count|quantity/.test(key) ? money(value) : String(value)}</dd>
                    </div>
                  ))}
              </dl>
            )}
          </div>
        ))}
      </div>

      {details.warnings.length > 0 && (
        <div className="order-form-warnings">
          <strong>Warnings</strong>
          <ul>
            {details.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="order-form-note muted">Delivery: {details.delivery_note}</div>

      {details.duplicate_check_status === "WARNING" && sessionId && !confirmed && (
        <label className="order-form-ack">
          <input type="checkbox" checked={ackDuplicate} onChange={(e) => setAckDuplicate(e.target.checked)} />
          <span>I've checked this against the flagged duplicate order and want to proceed anyway.</span>
        </label>
      )}

      <div className="order-form-footer">
        <span className={badgeClass(statusLabel)}>{statusLabel}</span>
        <div className="order-form-actions">
          <button className={`chip ${dirty ? "attention" : ""}`} onClick={submitRecheck} disabled={rechecking}>
            {rechecking ? "Rechecking…" : dirty ? "Recheck Order (edited)" : "Recheck Order"}
          </button>
          {sessionId && !confirmed && (
            <button
              className="primary-button"
              onClick={() => onConfirm(ackDuplicate)}
              disabled={confirming || dirty || (details.duplicate_check_status === "WARNING" && !ackDuplicate)}
              title={dirty ? "Recheck the edited order before confirming" : details.duplicate_check_status === "WARNING" && !ackDuplicate ? "Acknowledge the duplicate warning above to confirm" : undefined}
            >
              {confirming ? "Confirming…" : pricing ? `Confirm Order · ${money(pricing.total)}` : "Confirm Order"}
            </button>
          )}
          {confirmed && (
            <div className="confirmed-banner">
              <CheckIcon size={14} strokeWidth={3} />
              {confirmMessage || "Order confirmed."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
