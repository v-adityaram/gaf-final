import type { OrderLine, Pricing } from "../types";
import { money, percent } from "../lib/format";

function plural(n: number, unit: string): string {
  const u = unit.toLowerCase();
  if (n === 1) return `${n} ${u.replace(/s$/, "")}`;
  return `${n} ${u.endsWith("s") ? u : `${u}s`}`;
}

function qtyText(line: OrderLine): string {
  if (line.converted_quantity !== line.quantity || line.converted_unit !== line.unit) {
    const from = line.unit.toLowerCase().startsWith("sq") ? `${line.quantity} sq` : plural(line.quantity, line.unit);
    return `${from} = ${plural(line.converted_quantity, line.converted_unit)}`;
  }
  return plural(line.quantity, line.unit);
}

export default function PricingTable({ pricing, lines, showCommission = true }: { pricing: Pricing; lines: OrderLine[]; showCommission?: boolean }) {
  const included = lines.filter((l) => l.included);
  const commission = showCommission ? pricing.commission : null;
  const next = pricing.next_volume_tier;
  return (
    <div className="pricing-table-wrap">
      <table className="pricing-table">
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">Product</th>
            <th scope="col">Qty</th>
            <th scope="col" className="num">
              Unit
            </th>
            <th scope="col" className="num">
              Subtotal
            </th>
          </tr>
        </thead>
        <tbody>
          {included.map((line) => (
            <tr key={line.line_no} className={line.source === "add_on" ? "add-on" : undefined}>
              <td className="mono">{line.line_no}</td>
              <td>
                <span className="pricing-product">
                  {line.swatch_hex && <span className="swatch-dot" style={{ background: line.swatch_hex }} aria-hidden="true" />}
                  <span>
                    {line.product}
                    {line.colour && <span className="pricing-colour"> &middot; {line.colour}</span>}
                  </span>
                </span>
              </td>
              <td className="qty">{qtyText(line)}</td>
              <td className="num">
                {money(line.unit_price)}
                <span className="pricing-unit">/{line.price_unit}</span>
              </td>
              <td className="num">{money(line.line_subtotal)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          {pricing.discounts.map((d) => (
            <tr key={d.discount_id} className="discount-row">
              <td />
              <td colSpan={3}>
                <span className="pricing-discount">
                  {d.badge && <span className="tiny-chip accent">{d.badge}</span>}
                  <span>{d.name}</span>
                  <span className="pricing-colour">{percent(d.percent)}</span>
                </span>
              </td>
              <td className="num ok">&minus;{money(d.amount)}</td>
            </tr>
          ))}
          <tr className="sum-row">
            <td />
            <td colSpan={3}>Subtotal</td>
            <td className="num">{money(pricing.subtotal)}</td>
          </tr>
          {pricing.discount_total > 0 && (
            <tr className="sum-row">
              <td />
              <td colSpan={3}>Discounts</td>
              <td className="num ok">&minus;{money(pricing.discount_total)}</td>
            </tr>
          )}
          <tr className="total-row">
            <td />
            <td colSpan={3}>Order total</td>
            <td className="num">{money(pricing.total)}</td>
          </tr>
          {commission && (
            <tr className="muted-row">
              <td />
              <td colSpan={3}>Rep commission ({percent(commission.rate, 1)})</td>
              <td className="num">{money(commission.amount)}</td>
            </tr>
          )}
        </tfoot>
      </table>
      {next && (
        <p className="pricing-next-tier">
          Add {next.squares_short} more square{next.squares_short === 1 ? "" : "s"} to unlock {next.name} ({percent(next.percent)})
        </p>
      )}
    </div>
  );
}
