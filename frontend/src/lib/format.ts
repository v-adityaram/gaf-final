// Shared number/date formatting so every card, table and badge renders
// money and timestamps the same way.
const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export const money = (v: number | null | undefined): string => (v === null || v === undefined || Number.isNaN(v) ? "N/A" : usd.format(v));

// "2025-09-16T08:12:00Z" -> "Sep 16, 08:12". Falls back to the raw string
// when the input is not parseable so a bad payload never blanks a row.
export function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const datePart = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const timePart = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${datePart}, ${timePart}`;
}

// Rates arrive as fractions (0.03) or already-scaled (5); values above 1
// are treated as whole percentages. Trailing ".0" is kept only when digits
// is given explicitly, so "3.0%" for commission and "5%" for tiers.
export function percent(v: number, digits?: number): string {
  const scaled = v > 1 ? v : v * 100;
  if (digits !== undefined) return `${scaled.toFixed(digits)}%`;
  return `${Number.isInteger(scaled) ? scaled : scaled.toFixed(1)}%`;
}
