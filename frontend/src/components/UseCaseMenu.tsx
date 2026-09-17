import { useCallback, useMemo, useRef, useState } from "react";
import type { UseCase } from "../types";
import { useDismiss } from "../lib/dismiss";
import { ChevronIcon } from "./Icons";

export default function UseCaseMenu({ useCases, onPick }: { useCases: UseCase[]; onPick: (useCase: UseCase) => void }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, close, rootRef);

  const groups = useMemo(() => {
    const order: string[] = [];
    const byGroup = new Map<string, UseCase[]>();
    for (const uc of useCases) {
      if (!byGroup.has(uc.group)) {
        byGroup.set(uc.group, []);
        order.push(uc.group);
      }
      byGroup.get(uc.group)?.push(uc);
    }
    return order.map((g) => ({ group: g, items: byGroup.get(g) ?? [] }));
  }, [useCases]);

  return (
    <div className="usecase-root" ref={rootRef}>
      <button
        type="button"
        className={`chip subtle usecase-trigger${open ? " open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={useCases.length === 0}
      >
        <span className="usecase-trigger-label">Demo scenarios</span>
        <ChevronIcon size={14} className={`chev${open ? " up" : ""}`} />
      </button>
      {open && (
        <div className="usecase-menu" role="menu" aria-label="Demo scenarios">
          {groups.map(({ group, items }) => (
            <div key={group} className="usecase-group" role="group" aria-label={group}>
              <div className="usecase-group-title">{group}</div>
              {items.map((uc) => (
                <button
                  key={uc.id}
                  type="button"
                  role="menuitem"
                  className="usecase-item"
                  onClick={() => {
                    onPick(uc);
                    setOpen(false);
                  }}
                >
                  <span className="usecase-title">{uc.title}</span>
                  <span className="usecase-expects">{uc.expects}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
