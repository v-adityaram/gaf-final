import { useCallback, useEffect, useState } from "react";
import { getInbox, getRepDashboard, getReps, getReviews, getUseCases } from "./api";
import EmailWindow from "./components/EmailWindow";
import Header, { type Tab } from "./components/Header";
import { ClipboardIcon, InboxIcon, PhoneIcon } from "./components/Icons";
import Sidebar, { type SidebarItem } from "./components/Sidebar";
import { useTheme } from "./hooks/useTheme";
import AssistantPage from "./pages/AssistantPage";
import MetricsPage from "./pages/MetricsPage";
import SmartOrderPage from "./pages/SmartOrderPage";
import WarrantyAdvisorPage from "./pages/WarrantyAdvisorPage";
import type { InboxEmail, RepDashboard, SalesRep, UseCase } from "./types";

const REP_KEY = "gaf-rep";
const SIDEBAR_KEY = "gaf-sidebar-collapsed";

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // storage unavailable
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("assistant");
  const { theme, toggleTheme } = useTheme();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => readStorage(SIDEBAR_KEY) === "1");

  // The signed-in sales rep (demo: pick one from the header). Every order
  // is tied to the account's own rep on the backend; this only decides
  // whose inbox/dashboard the UI shows.
  const [reps, setReps] = useState<SalesRep[]>([]);
  const [repId, setRepId] = useState<string | null>(() => readStorage(REP_KEY));
  const [dashboard, setDashboard] = useState<RepDashboard | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);

  const [useCases, setUseCases] = useState<UseCase[]>([]);
  const [pendingReviews, setPendingReviews] = useState(0);

  const [inbox, setInbox] = useState<InboxEmail[]>([]);
  const [inboxLoading, setInboxLoading] = useState(false);
  const [emailOpen, setEmailOpen] = useState(false);
  const [emailSending, setEmailSending] = useState(false);
  const [processedEmailIds, setProcessedEmailIds] = useState<string[]>([]);

  // Cross-component requests into the Assistant page: a demo prompt to
  // prefill, emails to run through the assistant, and a call toggle.
  const [pendingPrompt, setPendingPrompt] = useState<{ text: string; nonce: number } | null>(null);
  const [emailRequest, setEmailRequest] = useState<{ ids: string[]; nonce: number } | null>(null);
  const [callRequest, setCallRequest] = useState(0);
  const [callActive, setCallActive] = useState(false);

  const currentRep = reps.find((r) => r.repId === repId) ?? null;

  useEffect(() => {
    getReps()
      .then((list) => {
        setReps(list);
        if (!list.some((r) => r.repId === repId)) setRepId(list[0]?.repId ?? null);
      })
      .catch(() => setReps([]));
    getUseCases().then(setUseCases).catch(() => setUseCases([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshDashboard = useCallback(() => {
    if (!repId) return;
    setDashboardLoading(true);
    getRepDashboard(repId)
      .then(setDashboard)
      .catch(() => setDashboard(null))
      .finally(() => setDashboardLoading(false));
  }, [repId]);

  const refreshReviews = useCallback(() => {
    getReviews("pending")
      .then((r) => setPendingReviews(r.reviews.length))
      .catch(() => setPendingReviews(0));
  }, []);

  const refreshInbox = useCallback(() => {
    if (!repId) return;
    setInboxLoading(true);
    getInbox(repId)
      .then(setInbox)
      .catch(() => setInbox([]))
      .finally(() => setInboxLoading(false));
  }, [repId]);

  useEffect(() => {
    if (!repId) return;
    writeStorage(REP_KEY, repId);
    setDashboard(null);
    setProcessedEmailIds([]);
    refreshDashboard();
    refreshInbox();
  }, [repId, refreshDashboard, refreshInbox]);

  useEffect(() => {
    refreshReviews();
  }, [refreshReviews]);

  function toggleSidebar() {
    setSidebarCollapsed((c) => {
      writeStorage(SIDEBAR_KEY, c ? "0" : "1");
      return !c;
    });
  }

  function pickUseCase(useCase: UseCase) {
    setActiveTab("assistant");
    setPendingPrompt({ text: useCase.prompt, nonce: Date.now() });
  }

  function sendEmails(ids: string[]) {
    if (ids.length === 0) return;
    setEmailSending(true);
    setActiveTab("assistant");
    setEmailRequest({ ids, nonce: Date.now() });
  }

  function handleEmailsProcessed(ids: string[]) {
    setEmailSending(false);
    setProcessedEmailIds((prev) => Array.from(new Set([...prev, ...ids])));
    refreshDashboard();
    refreshReviews();
  }

  function handleActivity() {
    refreshDashboard();
    refreshReviews();
  }

  const unread = inbox.filter((e) => !processedEmailIds.includes(e.emailId)).length;
  const sidebarItems: SidebarItem[] = [
    { id: "inbox", label: "Customer inbox", icon: <InboxIcon />, badge: unread || null, active: emailOpen, onClick: () => setEmailOpen((o) => !o) },
    {
      id: "call",
      label: callActive ? "End live call" : "Live call",
      icon: <PhoneIcon />,
      active: callActive,
      onClick: () => {
        setActiveTab("assistant");
        setCallRequest((n) => n + 1);
      },
    },
    { id: "reviews", label: "Review queue", icon: <ClipboardIcon />, badge: pendingReviews || null, active: activeTab === "metrics", onClick: () => setActiveTab("metrics") },
  ];

  return (
    <>
      <Header
        activeTab={activeTab}
        onTabChange={setActiveTab}
        theme={theme}
        onToggleTheme={toggleTheme}
        useCases={useCases}
        onPickUseCase={pickUseCase}
        reps={reps}
        currentRepId={repId}
        dashboard={dashboard}
        dashboardLoading={dashboardLoading}
        onSelectRep={setRepId}
      />
      <div className={`app-body ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
        <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} items={sidebarItems} />
        {/* All four tabs stay mounted the whole session -- switching tabs
            only hides/shows them, so drafts and chat logs survive. */}
        <main className="app-main">
          <div hidden={activeTab !== "assistant"}>
            <AssistantPage
              active={activeTab === "assistant"}
              rep={currentRep}
              pendingPrompt={pendingPrompt}
              emailRequest={emailRequest}
              onEmailsProcessed={handleEmailsProcessed}
              callRequest={callRequest}
              onCallStateChange={setCallActive}
              onActivity={handleActivity}
            />
          </div>
          <div hidden={activeTab !== "order"}>
            <SmartOrderPage onActivity={handleActivity} />
          </div>
          <div hidden={activeTab !== "warranty"}>
            <WarrantyAdvisorPage onActivity={handleActivity} />
          </div>
          <div hidden={activeTab !== "metrics"}>
            <MetricsPage active={activeTab === "metrics"} repId={repId} onReviewsChanged={refreshReviews} />
          </div>
        </main>
      </div>
      <EmailWindow
        open={emailOpen}
        onClose={() => setEmailOpen(false)}
        emails={inbox}
        loading={inboxLoading}
        sending={emailSending}
        processedIds={processedEmailIds}
        onSend={sendEmails}
        repName={currentRep?.name ?? null}
      />
    </>
  );
}
