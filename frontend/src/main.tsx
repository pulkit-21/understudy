import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { AuthProvider, useAuth } from "./auth";
import { LoginPage } from "./pages/LoginPage";
import { TracesPage } from "./pages/TracesPage";
import { TracePage } from "./pages/TracePage";
import { WorkflowPage } from "./pages/WorkflowPage";
import { RunPage } from "./pages/RunPage";
import { RunsPage } from "./pages/RunsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { Icon } from "./Icon";
import "./styles.css";

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
        <div className="brand"><span className="logo">U</span> Understudy</div>
        <NavItem to="/" end icon="dashboard" label="Dashboard" />
        <NavItem to="/workflows" icon="workflows" label="Workflows" />
        <NavItem to="/runs" icon="runs" label="Runs" />
        <NavItem to="/approvals" icon="approvals" label="Approvals" badge={pending} />
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
        <div className="sb-user">
          <div className="who">{user?.email}</div>
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
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </div>
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
