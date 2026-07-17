import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, TraceSummary, WorkflowSpec } from "../api";

export function TracesPage() {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [workflows, setWorkflows] = useState<WorkflowSpec[] | null>(null);
  const [traces, setTraces] = useState<TraceSummary[] | null>(null);
  const [inducing, setInducing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showHow, setShowHow] = useState(false);

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

  // returning from a browser recording session
  useEffect(() => {
    if (sp.get("recorded")) {
      setNotice("✓ Demonstration recorded. Click “Learn this workflow” below to turn it into a runnable workflow.");
      setSp({}, { replace: true });
    }
  }, [sp, setSp]);

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

  // Launch the in-browser recorder: go to Vendra with record mode on. The
  // recorder script (served into the mock apps) captures the demonstration and
  // POSTs it back, returning here with ?recorded=.
  function startRecording() {
    window.location.href = "/portal?record=1";
  }

  const firstRun = workflows?.length === 0 && (traces?.length ?? 0) > 0;

  return (
    <div className="container">
      <div className="toolbar">
        <div className="grow">
          <h1 className="page-title" style={{ margin: 0 }}>Workflows</h1>
        </div>
        <button className="btn primary" onClick={() => setShowHow(true)}>
          ⏺ Teach a new workflow
        </button>
      </div>

      {showHow && (
        <div className="banner info" style={{ flexDirection: "column", alignItems: "stretch" }}>
          <div><b>Teach Understudy by doing the task once.</b></div>
          <ol style={{ margin: "8px 0", paddingLeft: 20 }}>
            <li>You'll land in <b>Vendra</b> (the invoice portal) with recording on.</li>
            <li>Open an invoice, read it, switch to <b>LedgerOne</b>, enter the bill, and post it.</li>
            <li>Click <b>Stop &amp; save</b> in the recorder widget — Understudy learns the procedure.</li>
          </ol>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn primary" onClick={startRecording}>Start recording in Vendra →</button>
            <button className="btn" onClick={() => setShowHow(false)}>Cancel</button>
          </div>
        </div>
      )}
      <p className="page-sub">
        A workflow is a procedure Understudy learned by watching one
        demonstration. Open one to review and edit it, or run it on new data.
      </p>

      {notice && <div className="banner info">{notice}</div>}
      {error && <div className="banner error">{error}</div>}
      {firstRun && (
        <div className="banner success">
          👋 Start here: pick the recorded demonstration below and click
          <strong> Learn this workflow</strong> — Understudy will learn the procedure,
          then you can run it on any invoice.
        </div>
      )}

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
          No demonstrations recorded yet. Record one with the button above, or
          seed the demo with <code>python scripts/seed_demo.py</code>.
        </div>
      ) : (
        <div className="card">
          {traces.map((t) => (
            <div className="row" key={t.id}>
              <div className="grow">
                <div className="title">
                  <a href={`/traces/${t.id}`}
                     onClick={(e) => { e.preventDefault(); nav(`/traces/${t.id}`); }}>
                    {t.name}
                  </a>
                </div>
                <div className="meta">{t.events} events · {t.id}</div>
              </div>
              <button
                className="btn sm primary"
                disabled={inducing !== null}
                onClick={() => induce(t.id)}
              >
                {inducing === t.id ? "Learning…" : "Learn this workflow"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
