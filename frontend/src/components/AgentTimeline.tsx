import { AlertIcon, CheckIcon, XIcon } from "./Icons";

interface AgentTimelineProps {
  steps: string[];
}

function iconFor(step: string) {
  const lowered = step.toLowerCase();
  if (lowered.includes("could not") || lowered.includes("needs clarification")) {
    return { cls: "icon err", node: <XIcon size={11} strokeWidth={3} /> };
  }
  if (lowered.includes("possible duplicate") || lowered.includes("expert-only") || lowered.includes("urgent")) {
    return { cls: "icon warn", node: <AlertIcon size={11} strokeWidth={2.5} /> };
  }
  return { cls: "icon", node: <CheckIcon size={11} strokeWidth={3} /> };
}

export default function AgentTimeline({ steps }: AgentTimelineProps) {
  if (steps.length === 0) return null;

  return (
    <ul className="timeline">
      {steps.map((step, idx) => {
        const { cls, node } = iconFor(step);
        return (
          <li key={idx}>
            <span className={cls}>{node}</span>
            <span>{step}</span>
          </li>
        );
      })}
    </ul>
  );
}
