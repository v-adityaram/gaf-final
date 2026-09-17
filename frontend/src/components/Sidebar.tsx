import type { ReactNode } from "react";
import { ChevronLeftIcon } from "./Icons";

export interface SidebarItem {
  id: string;
  label: string;
  icon: ReactNode;
  badge?: number | null;
  active?: boolean;
  onClick: () => void;
}

// Vertical rail on desktop, icon-only bottom bar on phones (via CSS). The
// same markup serves both; only the toggle is hidden on the bottom bar.
export default function Sidebar({ collapsed, onToggle, items }: { collapsed: boolean; onToggle: () => void; items: SidebarItem[] }) {
  return (
    <nav className={`app-sidebar${collapsed ? " collapsed" : ""}`} aria-label="Workspace">
      <ul className="sidebar-items">
        {items.map((item) => {
          const badge = item.badge ?? 0;
          const label = badge > 0 ? `${item.label} (${badge})` : item.label;
          return (
            <li key={item.id}>
              <button
                type="button"
                className={`sidebar-item${item.active ? " active" : ""}`}
                onClick={item.onClick}
                title={label}
                aria-label={label}
                aria-current={item.active ? "page" : undefined}
              >
                <span className="sidebar-icon" aria-hidden="true">
                  {item.icon}
                  {badge > 0 && <span className="sidebar-bubble">{badge > 99 ? "99+" : badge}</span>}
                </span>
                <span className="sidebar-label">{item.label}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        className="sidebar-toggle"
        onClick={onToggle}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        title={collapsed ? "Expand" : "Collapse"}
        aria-expanded={!collapsed}
      >
        <ChevronLeftIcon size={16} className={`chev${collapsed ? " flip" : ""}`} />
        <span className="sidebar-label">Collapse</span>
      </button>
    </nav>
  );
}
