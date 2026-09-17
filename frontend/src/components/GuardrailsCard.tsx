import { guardrailIcon } from "../lib/badge";
import type { GuardrailItem } from "../types";

interface GuardrailsCardProps {
  items?: GuardrailItem[];
}

// Compact, read-only summary of the checks the backend actually ran for
// this response (see backend/app/services/guardrails.py) -- never invented
// on the frontend. Shown after every order and warranty reply.
export default function GuardrailsCard({ items }: GuardrailsCardProps) {
  if (!items || items.length === 0) return null;
  return (
    <div className="guardrails-card">
      <span className="guardrails-title">Guardrails Applied</span>
      <ul>
        {items.map((item) => (
          <li key={item.label} className={`guardrail-${item.status.toLowerCase().replace(/[^a-z]/g, "")}`}>
            <span className="guardrail-icon" aria-hidden="true">
              {guardrailIcon(item.status)}
            </span>
            {item.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
