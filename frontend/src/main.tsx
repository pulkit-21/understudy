import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { TracesPage } from "./pages/TracesPage";
import { TracePage } from "./pages/TracePage";
import { WorkflowPage } from "./pages/WorkflowPage";
import { RunPage } from "./pages/RunPage";
import { RunsPage } from "./pages/RunsPage";
import "./styles.css";

function App() {
  return (
    <>
      <nav className="nav">
        <span className="brand">
          Understudy <small>learn a workflow, run it with a gate</small>
        </span>
        <NavLink to="/" end>Workflows</NavLink>
        <NavLink to="/runs">Runs</NavLink>
        <span className="spacer" />
        <a className="ext" href="/portal" target="_blank" rel="noreferrer">Vendra ↗</a>
        <a className="ext" href="/erp" target="_blank" rel="noreferrer">LedgerOne ↗</a>
        <a className="ext" href="/docs" target="_blank" rel="noreferrer">API ↗</a>
      </nav>
      <Routes>
        <Route path="/" element={<TracesPage />} />
        <Route path="/traces/:id" element={<TracePage />} />
        <Route path="/workflows/:id" element={<WorkflowPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:id" element={<RunPage />} />
      </Routes>
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
