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
import "./styles.css";

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
    <>
      <nav className="nav">
        <span className="brand">
          Understudy <small>learn a workflow, run it with a gate</small>
        </span>
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/workflows">Workflows</NavLink>
        <NavLink to="/runs">Runs</NavLink>
        <NavLink to="/approvals">
          Approvals{pending > 0 && <span className="navbadge">{pending}</span>}
        </NavLink>
        <span className="spacer" />
        <a className="ext" href="/portal" target="_blank" rel="noreferrer">Vendra ↗</a>
        <a className="ext" href="/erp" target="_blank" rel="noreferrer">LedgerOne ↗</a>
        <span className="whoami">{user?.email}</span>
        <a className="ext" onClick={logout} style={{ cursor: "pointer" }}>Sign out</a>
      </nav>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/workflows" element={<TracesPage />} />
        <Route path="/traces/:id" element={<TracePage />} />
        <Route path="/workflows/:id" element={<WorkflowPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:id" element={<RunPage />} />
        <Route path="/approvals" element={<ApprovalsPage />} />
      </Routes>
    </>
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
