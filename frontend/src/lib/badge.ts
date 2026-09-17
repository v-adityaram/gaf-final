// Shared with MetricsPage.tsx, OrderForm.tsx and GuardrailsCard.tsx so a
// check/order/guardrail status (PASSED, WARNING, BLOCKED, CONFIRMED,
// FAILED, URGENT, ...) always maps to the same badge colour everywhere.
export function badgeClass(status?: string | null): string {
  const s = (status || "").toUpperCase();
  if (s.includes("CONFIRMED") || s.includes("PASSED") || s.includes("READY") || s.includes("ANSWERED") || s.includes("ANALYZED")) return "status-badge green";
  if (s.includes("WARNING") || s.includes("CLARIFICATION") || s.includes("ESCALATED")) return "status-badge amber";
  if (s.includes("BLOCKED") || s.includes("FAILED") || s.includes("ERROR") || s.includes("URGENT")) return "status-badge red";
  return "status-badge";
}

// The compact glyph GuardrailsCard prefixes each line with.
export function guardrailIcon(status?: string | null): string {
  const s = (status || "").toUpperCase();
  if (s.includes("URGENT")) return "\u{1F534}"; // 🔴
  if (s.includes("PASSED")) return "✓"; // ✓
  if (s.includes("WARNING")) return "⚠"; // ⚠
  if (s.includes("BLOCKED") || s.includes("FAILED") || s.includes("ERROR")) return "✕"; // ✗
  if (s.includes("ESCALATED")) return "⚠"; // ⚠
  return "•"; // · (N/A / unknown)
}
