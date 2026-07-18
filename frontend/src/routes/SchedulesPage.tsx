import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, Schedule, WorkflowSpec } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { SkeletonList } from "../components/Skeleton";

function when(ts: string | null) {
  if (!ts) return "—";
  try { return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return ts; }
}

export function SchedulesPage() {
  const nav = useNavigate();
  const { data: schedules, loading, reload } = useAsync(() => api.listSchedules(), []);
  const { data: workflows } = useAsync(() => api.listWorkflows(), []);
  const [wfId, setWfId] = useState("");
  const [interval, setInterval] = useState(60);
  const [params, setParams] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const wf: WorkflowSpec | undefined = workflows?.find((w) => w.id === wfId);

  async function create() {
    if (!wfId) return;
    setBusy(true); setError(null);
    try {
      await api.createSchedule(wfId, params, interval);
      setWfId(""); setParams({}); setInterval(60);
      reload();
    } catch (e) { setError(e instanceof ApiError ? String(e.detail) : String(e)); }
    finally { setBusy(false); }
  }
  async function toggle(s: Schedule) {
    await api.toggleSchedule(s.id, !s.enabled).catch(() => {});
    reload();
  }
  async function remove(id: string) {
    await api.deleteSchedule(id).catch(() => {});
    reload();
  }

  return (
    <div className="container">
      <h1 className="page-title">Schedules</h1>
      <p className="page-sub">
        Run a workflow on a recurring interval, unattended. Scheduled runs still
        pause at their approval gate — a schedule automates <em>starting</em> work,
        never <em>approving</em> it.
      </p>
      {error && <div className="banner error">{error}</div>}

      {/* create */}
      <div className="card" style={{ padding: 18, marginBottom: 18 }}>
        <div className="section-h" style={{ marginTop: 0 }}>New schedule</div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label style={{ flex: "1 1 240px" }}>
            <div className="meta">Workflow</div>
            <select className="input" value={wfId}
                    onChange={(e) => { setWfId(e.target.value); setParams({}); }}>
              <option value="">Select a workflow…</option>
              {(workflows ?? []).map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
          </label>
          <label style={{ flex: "0 0 160px" }}>
            <div className="meta">Every (minutes)</div>
            <input className="input" type="number" min={1} value={interval}
                   onChange={(e) => setInterval(Math.max(1, Number(e.target.value)))} />
          </label>
        </div>
        {wf && wf.parameters.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div className="meta">Inputs</div>
            {wf.parameters.map((p) => (
              <div key={p.key} style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6 }}>
                <span className="chip param">{p.key}</span>
                <input className="input mono" placeholder={p.example ?? ""}
                       value={params[p.key] ?? ""}
                       onChange={(e) => setParams({ ...params, [p.key]: e.target.value })} />
              </div>
            ))}
          </div>
        )}
        <button className="btn primary" disabled={!wfId || busy} onClick={create}
                style={{ marginTop: 14 }}>
          {busy ? "Creating…" : "Create schedule"}
        </button>
      </div>

      {/* list */}
      {loading ? <SkeletonList rows={2} />
        : (schedules ?? []).length === 0 ? (
          <div className="card empty">No schedules yet. Create one above.</div>
        ) : (
          <div className="card">
            {(schedules ?? []).map((s) => {
              const name = workflows?.find((w) => w.id === s.workflow_id)?.name ?? s.workflow_id;
              return (
                <div className="row" key={s.id}>
                  <span className={"badge " + (s.enabled ? "gate" : "read")}>
                    {s.enabled ? "active" : "paused"}
                  </span>
                  <div className="grow">
                    <div className="title">
                      <a onClick={() => nav(`/workflows/${s.workflow_id}`)}
                         style={{ cursor: "pointer" }}>{name}</a>
                    </div>
                    <div className="meta">
                      every {s.interval_minutes} min ·{" "}
                      {Object.entries(s.params).map(([k, v]) => `${k}=${v}`).join(", ") || "no inputs"}
                      {" · "}next {when(s.next_run_at)} · last {when(s.last_run_at)}
                    </div>
                  </div>
                  <button className="btn sm" onClick={() => toggle(s)}>
                    {s.enabled ? "Pause" : "Resume"}
                  </button>
                  <button className="btn sm danger" onClick={() => remove(s.id)}>Delete</button>
                </div>
              );
            })}
          </div>
        )}
    </div>
  );
}
