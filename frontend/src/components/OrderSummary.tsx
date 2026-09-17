const LINE = /^([A-Za-z][A-Za-z &/-]{1,40}):\s*(.*)$/;
const ITEM = /^\s{2,}(\d+)\.\s+(.+)$/;

interface OrderSummaryProps {
  text: string;
}

// The Smart Order Agent's message is a fixed "Label: value" template
// (see order_orchestrator.py), with an indented "1. ..." list under
// "Lines:". Render it as a summary grid when it matches that shape;
// anything else (clarifications, blocked reasons) stays prose.
export default function OrderSummary({ text }: OrderSummaryProps) {
  const lines = text.split("\n").filter((l) => l.trim().length > 0);
  const parsed = lines.map((line) => (ITEM.test(line) ? null : line.match(LINE)));
  if (parsed.filter(Boolean).length < 3) {
    return <span className="bubble-text">{text}</span>;
  }

  const rows: JSX.Element[] = [];
  let pendingItems: string[] = [];
  let pendingLabel: string | null = null;

  const flush = (key: number) => {
    if (pendingLabel === null) return;
    rows.push(
      <div key={`items-${key}`} className="row">
        <dt>{pendingLabel}</dt>
        <dd>
          <ol className="order-summary-lines">
            {pendingItems.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ol>
        </dd>
      </div>
    );
    pendingItems = [];
    pendingLabel = null;
  };

  lines.forEach((line, idx) => {
    const item = line.match(ITEM);
    if (item) {
      pendingItems.push(item[2]);
      return;
    }
    flush(idx);
    const match = parsed[idx];
    if (!match) {
      rows.push(
        <div key={idx} className="row prose">
          <dd>{line}</dd>
        </div>
      );
      return;
    }
    const [, label, value] = match;
    if (value === "") {
      pendingLabel = label;
      return;
    }
    const kind = label === "Warnings" ? "warn" : label === "Final Status" ? "final" : label === "Order Total" ? "total" : "";
    rows.push(
      <div key={idx} className={`row ${kind}`}>
        <dt>{label}</dt>
        <dd>{value}</dd>
      </div>
    );
  });
  flush(lines.length);

  return <dl className="order-summary">{rows}</dl>;
}
