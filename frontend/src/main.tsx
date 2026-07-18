import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { api } from "./lib/api";
import { AuthProvider, useAuth } from "./lib/auth";
import { LoginPage } from "./routes/LoginPage";
import { TracesPage } from "./routes/TracesPage";
import { TracePage } from "./routes/TracePage";
import { WorkflowPage } from "./routes/WorkflowPage";
import { RunPage } from "./routes/RunPage";
import { RunsPage } from "./routes/RunsPage";
import { DashboardPage } from "./routes/DashboardPage";
import { ApprovalsPage } from "./routes/ApprovalsPage";
import { SettingsPage } from "./routes/SettingsPage";
import { AssistantPage } from "./routes/AssistantPage";
import { TeamPage } from "./routes/TeamPage";
import { AuditPage } from "./routes/AuditPage";
import { Tour } from "./components/Tour";
import { CommandPalette } from "./components/CommandPalette";
import { Icon } from "./components/Icon";
import "./styles/styles.css";

// apply saved theme before first paint
const savedTheme = localStorage.getItem("understudy_theme") || "light";
document.documentElement.dataset.theme = savedTheme;

function ThemeToggle({ dark, onToggle }: { dark: boolean; onToggle: () => void }) {
  return (
    <button className="theme-toggle" onClick={onToggle}>
      <Icon name={dark ? "sun" : "moon"} size={17} />
      <span>{dark ? "Light mode" : "Dark mode"}</span>
    </button>
  );
}

function NavItem({ to, icon, label, badge, end }: {
  to: string; icon: string; label: string; badge?: number; end?: boolean;
}) {
  return (
    <NavLink to={to} end={end}
             className={({ isActive }) => "navitem" + (isActive ? " active" : "")}>
      <Icon name={icon} />
      <span>{label}</span>
      {badge ? <span className="navbadge">{badge}</span> : null}
    </NavLink>
  );
}

function Shell() {
  const { user, logout } = useAuth();
  const [pending, setPending] = useState(0);
  const [tour, setTour] = useState(() => !localStorage.getItem("understudy_tour_seen"));
  const [cmdk, setCmdk] = useState(false);
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === "dark");
  function closeTour() { localStorage.setItem("understudy_tour_seen", "1"); setTour(false); }
  function toggleTheme() {
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("understudy_theme", next);
    setDark(!dark);
  }

  // ⌘K / Ctrl+K opens the command palette from anywhere
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdk((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // keep the approvals badge fresh — the queue changes as runs hit gates
  useEffect(() => {
    let alive = true;
    const tick = () => api.dashboard()
      .then((d) => { if (alive) setPending(d.pending_approvals); })
      .catch(() => {});
    tick();
    const t = setInterval(tick, 8000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="brand">
          <span className="logo">U</span>
          <span>Understudy<small className="brand-sub">workflow automation</small></span>
        </div>
        <button className="sb-search" onClick={() => setCmdk(true)}>
          <Icon name="search" size={16} />
          <span>Search…</span>
          <kbd className="sb-kbd">⌘K</kbd>
        </button>
        <NavItem to="/" end icon="dashboard" label="Dashboard" />
        <NavItem to="/assistant" icon="chat" label="Assistant" />
        <NavItem to="/workflows" icon="workflows" label="Workflows" />
        <NavItem to="/runs" icon="runs" label="Runs" />
        <NavItem to="/approvals" icon="approvals" label="Approvals" badge={pending} />
        <NavItem to="/audit" icon="book" label="Audit log" />
        <NavItem to="/team" icon="team" label="Team" />
        <NavItem to="/settings" icon="settings" label="Settings" />

        <div className="sb-section">Mock apps</div>
        <a className="navitem" href="/portal" target="_blank" rel="noreferrer">
          <Icon name="external" /><span>Vendra portal</span>
        </a>
        <a className="navitem" href="/erp" target="_blank" rel="noreferrer">
          <Icon name="external" /><span>LedgerOne ERP</span>
        </a>
        <a className="navitem" href="/docs" target="_blank" rel="noreferrer">
          <Icon name="file" /><span>API docs</span>
        </a>

        <div className="spacer" />
        <ThemeToggle dark={dark} onToggle={toggleTheme} />
        <div className="sb-user">
          <div className="who">{user?.email}<br /><span style={{ opacity: .7 }}>admin · workspace</span></div>
          <a className="navitem" onClick={logout} style={{ cursor: "pointer" }}>
            <Icon name="logout" /><span>Sign out</span>
          </a>
        </div>
      </aside>
      <div className="main">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/workflows" element={<TracesPage />} />
          <Route path="/traces/:id" element={<TracePage />} />
          <Route path="/workflows/:id" element={<WorkflowPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/runs/:id" element={<RunPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/assistant" element={<AssistantPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/team" element={<TeamPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </div>
      <button className="help-fab" title="Take a tour" onClick={() => setTour(true)}>?</button>
      {tour && <Tour onClose={closeTour} />}
      <CommandPalette
        open={cmdk}
        onClose={() => setCmdk(false)}
        onToggleTheme={toggleTheme}
        onStartTour={() => setTour(true)}
        onLogout={logout}
      />
    </div>
  );
}

function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="spinner">Loading…</div>;
  if (!user) return <LoginPage />;
  return <Shell />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>,
);
