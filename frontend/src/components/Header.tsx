import GafLogo from "./GafLogo";
import { MoonIcon, SunIcon } from "./Icons";
import RepBadge from "./RepBadge";
import UseCaseMenu from "./UseCaseMenu";
import type { Theme } from "../hooks/useTheme";
import type { RepDashboard, SalesRep, UseCase } from "../types";

export type Tab = "assistant" | "order" | "warranty" | "metrics";

const TABS: Array<{ id: Tab; label: string; short: string }> = [
  { id: "assistant", label: "Assistant", short: "Assistant" },
  { id: "order", label: "Smart Order Helper", short: "Orders" },
  { id: "warranty", label: "Product & Warranty Advisor", short: "Warranty" },
  { id: "metrics", label: "Metrics & Review Queue", short: "Metrics" },
];

interface HeaderProps {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  theme: Theme;
  onToggleTheme: () => void;
  useCases: UseCase[];
  onPickUseCase: (useCase: UseCase) => void;
  reps: SalesRep[];
  currentRepId: string | null;
  dashboard: RepDashboard | null;
  dashboardLoading: boolean;
  onSelectRep: (repId: string) => void;
}

export default function Header({
  activeTab,
  onTabChange,
  theme,
  onToggleTheme,
  useCases,
  onPickUseCase,
  reps,
  currentRepId,
  dashboard,
  dashboardLoading,
  onSelectRep,
}: HeaderProps) {
  return (
    <header className="app-header">
      <div className="header-row">
        <div className="brand">
          <GafLogo size={38} />
          <div className="brand-text">
            <h1>Sales Assistant</h1>
            <div className="subtitle">Orders · Warranty · Contractors</div>
          </div>
        </div>

        <nav className="tabs" aria-label="Assistants">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              className={`tab-button ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => onTabChange(tab.id)}
              aria-current={activeTab === tab.id ? "page" : undefined}
            >
              <span className="tab-label-long">{tab.label}</span>
              <span className="tab-label-short">{tab.short}</span>
            </button>
          ))}
        </nav>

        <div className="header-tools">
          {useCases.length > 0 && <UseCaseMenu useCases={useCases} onPick={onPickUseCase} />}
          <RepBadge reps={reps} currentRepId={currentRepId} dashboard={dashboard} loading={dashboardLoading} onSelectRep={onSelectRep} />
          <button
            className="icon-button ghost theme-toggle"
            onClick={onToggleTheme}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Light mode" : "Dark mode"}
          >
            {theme === "dark" ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </div>
    </header>
  );
}
