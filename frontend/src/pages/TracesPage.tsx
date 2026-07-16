import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, TraceSummary, WorkflowSpec } from "../api";

export function TracesPage() {
  const nav = useNavigate();
  const [workflows, setWorkflows] = useState<WorkflowSpec[] | null>(null);
  const [traces, setTraces] = useState<TraceSummary[] | null>(null);
  const [inducing, setInducing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [wf, tr] = await Promise.all([api.listWorkflows(), api.listTraces()]);
      setWorkflows(wf);
      setTraces(tr);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    }
  }
  useEffect(() => { load(); }, []);

  async function induce(traceId: string) {
    setInducing(traceId);
    setError(null);
    try {
      const res = await api.induce(traceId, true);
      nav(`/workflows/${res.workflow.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
      setInducing(null);
    }
  }

  return (
    <div className="container">
      <h1 className="page-title">Workflows</h1>
      <p className="page-sub">
        A workflow is a procedure Understudy learned by watching one
        demonstration. Open one to review and edit it, or run it on new data.
      </p>

      {error && <div className="banner error">{error}</div>}

      {workflows === null ? (
        <div className="spinner">Loading…</div>
      ) : workflows.length === 0 ? (
        <div className="card empty">
          No workflows yet. Induce one from a demonstration below.
        </div>
      ) : (
        <div className="card">
          {workflows.map((w) => (
            <div className="row" key={w.id}>
              <div className="grow">
                <div className="title">
                  <a href={`/workflows/${w.id}`}
                     onClick={(e) => { e.preventDefault(); nav(`/workflows/${w.id}`); }}>
                    {w.name}
                  </a>
                </div>
                <div className="meta">
                  {w.steps.length} steps · v{w.version} ·{" "}
                  {w.parameters.length === 0
                    ? "no inputs"
                    : `input: ${w.parameters.map((p) => p.key).join(", ")}`}
                </div>
              </div>
              <button className="btn sm" onClick={() => nav(`/workflows/${w.id}`)}>
                Open
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="section-h">Recorded demonstrations</div>
      {traces === null ? (
        <div className="spinner">Loading…</div>
      ) : traces.length === 0 ? (
        <div className="card empty">
          No demonstrations recorded yet. Record one locally with{" "}
          <code>POST /api/recordings/start</code>, or seed the demo with{" "}
          <code>python scripts/seed_demo.py</code>.
        </div>
      ) : (
        <div className="card">
          {traces.map((t) => (
            <div className="row" key={t.id}>
              <div className="grow">
                <div className="title">{t.name}</div>
                <div className="meta">{t.events} events · {t.id}</div>
              </div>
              <button
                className="btn sm primary"
                disabled={inducing !== null}
                onClick={() => induce(t.id)}
              >
                {inducing === t.id ? "Learning…" : "Induce workflow"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
