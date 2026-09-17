import { useEffect, type RefObject } from "react";

// Close a popover/menu on Escape or on a pointer-down outside `ref`.
// Shared by RepBadge, UseCaseMenu and EmailWindow (Escape only there).
export function useDismiss(open: boolean, onClose: () => void, ref?: RefObject<HTMLElement>) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onPointer = (e: PointerEvent) => {
      if (!ref) return;
      const el = ref.current;
      if (el && e.target instanceof Node && !el.contains(e.target)) onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open, onClose, ref]);
}
