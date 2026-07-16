import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, TraceSummary, WorkflowSpec } from "../api";

export function TracesPage() {
  const nav = useNavigate();
  const [workflows, setWorkflows] = useState<WorkflowSpec[] | null>(null);
  const [traces, setTraces] = useState<TraceSummary[] | null>(null);
  const [inducing, setInducing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [recording, setRecording] = useState<{ id: string; name: string } | null>(null);
  const [busy, setBusy] = useState(false);

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

  async function startRecording() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const r = await api.startRecording("Demonstration");
      setRecording({ id: r.recording_id, name: r.name });
      setNotice(
        "A browser window opened — perform the task there, then click Stop.",
      );
    } catch (e) {
      // On a headless server the demonstration browser can't launch (503).
      setNotice(
        e instanceof ApiError && e.status === 503
          ? "Live recording needs a display, so it runs locally. On this hosted demo, use the seeded demonstration below (or POST a trace to /api/traces)."
          : (e instanceof ApiError ? String(e.detail) : String(e)),
      );
    } finally {
      setBusy(false);
    }
  }

  async function stopRecording() {
    if (!recording) return;
    setBusy(true);
    try {
      await api.stopRecording(recording.id);
      setRecording(null);
      setNotice("Recording saved. Induce a workflow from it below.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  }

  const firstRun = workflows?.length === 0 && (traces?.length ?? 0) > 0;

  return (
    <div className="container">
      <div className="toolbar">
        <div className="grow">
          <h1 className="page-title" style={{ margin: 0 }}>Workflows</h1>
        </div>
        {recording ? (
          <button className="btn danger" disabled={busy} onClick={stopRecording}>
            ⏺ Stop recording
          </button>
        ) : (
          <button className="btn" disabled={busy} onClick={startRecording}>
            ⏺ Record a demonstration
          </button>
        )}
      </div>
      <p className="page-sub">
        A workflow is a procedure Understudy learned by watching one
        demonstration. Open one to review and edit it, or run it on new data.
      </p>

      {notice && <div className="banner info">{notice}</div>}
      {error && <div className="banner error">{error}</div>}
      {firstRun && (
        <div className="banner success">
          👋 Start here: pick the recorded demonstration below and click
          <strong> Induce workflow</strong> — Understudy will learn the procedure,
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
                {inducing === t.id ? "Learning…" : "Induce workflow"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
