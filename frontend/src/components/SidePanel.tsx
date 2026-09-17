import { useEffect, useState, type ReactNode } from "react";
import { ChevronIcon } from "./Icons";

interface SidePanelProps {
  title: string;
  children: ReactNode;
}

const WIDE = "(min-width: 901px)";

// Collapsible on phones (where it sits below a full-height chat), open by
// default on wider screens where it lives in the sidebar.
export default function SidePanel({ title, children }: SidePanelProps) {
  const [open, setOpen] = useState(() => window.matchMedia(WIDE).matches);

  useEffect(() => {
    const mq = window.matchMedia(WIDE);
    const onChange = (e: MediaQueryListEvent) => {
      if (e.matches) setOpen(true);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return (
    <details className="panel side-panel" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>
        <span>{title}</span>
        <ChevronIcon size={16} className="chev" />
      </summary>
      <div className="panel-body">{children}</div>
    </details>
  );
}
