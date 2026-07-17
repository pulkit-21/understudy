import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { LoginPage } from "./pages/LoginPage";
import { TracesPage } from "./pages/TracesPage";
import { TracePage } from "./pages/TracePage";
import { WorkflowPage } from "./pages/WorkflowPage";
import { RunPage } from "./pages/RunPage";
import { RunsPage } from "./pages/RunsPage";
import { DashboardPage } from "./pages/DashboardPage";
import "./styles.css";

function Shell() {
  const { user, logout } = useAuth();
  return (
    <>
      <nav className="nav">
        <span className="brand">
          Understudy <small>learn a workflow, run it with a gate</small>
        </span>
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/workflows">Workflows</NavLink>
        <NavLink to="/runs">Runs</NavLink>
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
