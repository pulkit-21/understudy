import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  api, ApiError, WorkflowSpec, WorkflowStatusT, WorkflowStep, WorkflowVersion,
} from "../api";

function ValueChip({ value }: { value: string }) {
  const ex = value.match(/^\{\{\s*extract\.([\w.]+)\s*\}\}$/);
  if (ex) return <span className="chip extract">↳ read: {ex[1]}</span>;
  const pm = value.match(/^\{\{\s*([\w.]+)\s*\}\}$/);
  if (pm) return <span className="chip param">input: {pm[1]}</span>;
  return <span className="chip">"{value}"</span>;
}

function StepCard({ step, index, onIntent, onGate }: {
  step: WorkflowStep; index: number;
  onIntent: (v: string) => void; onGate: (v: boolean) => void;
}) {
  const testid = step.target?.testid;
  return (
    <div className={"step" + (step.risk === "commit" ? " commit" : "")}>
      <div className="num">{index + 1}</div>
      <div className="body">
        <textarea className="intent" rows={1} value={step.intent}
                  onChange={(e) => onIntent(e.target.value)} />
        <div className="detail">
          <span className="badge action">{step.action}</span>
          <span className={"badge " + step.risk}>{step.risk}</span>
          {step.url && (
            <span className="chip">{step.url.replace(/^https?:\/\/[^/]+/, "")}</span>
          )}
          {testid && <span className="chip">#{testid}</span>}
          {step.extract_key && <span className="chip extract">→ {step.extract_key}</span>}
          {step.value && <ValueChip value={step.value} />}
          {step.risk === "commit" && (
            <label className="gate-toggle" title="Irreversible steps must pause for a human">
              <input type="checkbox" checked={step.requires_approval}
                     onChange={(e) => onGate(e.target.checked)} />
              requires approval
            </label>
          )}
        </div>
      </div>
    </div>
  );
}

export function WorkflowPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [spec, setSpec] = useState<WorkflowSpec | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [params, setParams] = useState<Record<string, string>>({});
  const [starting, setStarting] = useState(false);
  const [batchText, setBatchText] = useState("");
  const [versions, setVersions] = useState<WorkflowVersion[] | null>(null);

  useEffect(() => {
    api.getWorkflow(id)
      .then((s) => {
        setSpec(s);
        setParams(Object.fromEntries(s.parameters.map((p) => [p.key, p.example ?? ""])));
      })
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, [id]);

  const gated = useMemo(
    () => spec?.steps.filter((s) => s.requires_approval).length ?? 0, [spec]);

  function edit(mut: (s: WorkflowSpec) => void) {
    if (!spec) return;
    const next = structuredClone(spec);
    mut(next);
    setSpec(next);
    setDirty(true);
    setSaved(false);
  }
  function fail(e: unknown) {
    setError(e instanceof ApiError ? String(e.detail) : String(e));
  }

  async function save() {
    if (!spec) return;
    setSaving(true); setProblems([]); setError(null);
    try {
      const updated = await api.saveWorkflow(id, spec);
      setSpec(updated); setDirty(false); setSaved(true); setVersions(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && Array.isArray(e.detail))
        setProblems(e.detail as string[]);
      else fail(e);
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus(status: WorkflowStatusT) {
    try { setSpec(await api.setWorkflowStatus(id, status)); } catch (e) { fail(e); }
  }
  async function duplicate() {
    try { nav(`/workflows/${(await api.duplicateWorkflow(id)).id}`); }
    catch (e) { fail(e); }
  }
  async function remove() {
    if (!confirm("Delete this workflow? This can't be undone.")) return;
    try { await api.deleteWorkflow(id); nav("/workflows"); } catch (e) { fail(e); }
  }
  async function loadVersions() {
    try { setVersions(await api.workflowVersions(id)); } catch (e) { fail(e); }
  }
  async function rollback(v: number) {
    try { setSpec(await api.rollbackWorkflow(id, v)); setVersions(null); }
    catch (e) { fail(e); }
  }

  async function run() {
    setStarting(true); setError(null);
    try {
      const { run_id } = await api.startRun(id, params);
      nav(`/runs/${run_id}`);
    } catch (e) { fail(e); setStarting(false); }
  }
  async function runBatch() {
    const values = batchText.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
    if (values.length === 0) return;
    setStarting(true); setError(null);
    try {
      const { batch_id } = await api.startBatch(id, values);
      nav(`/runs?batch=${batch_id}`);
    } catch (e) { fail(e); setStarting(false); }
  }

  if (error && !spec) return <div className="container"><div className="banner error">{error}</div></div>;
  if (!spec) return <div className="container"><div className="spinner">Loading…</div></div>;

  const policy = spec.approval_policy;

  return (
    <div className="container">
      <div className="toolbar">
        <a href="/workflows" onClick={(e) => { e.preventDefault(); nav("/workflows"); }}>← Workflows</a>
        <div className="grow" />
        <select className="input" style={{ width: "auto" }} value={spec.status}
                onChange={(e) => changeStatus(e.target.value as WorkflowStatusT)}>
          <option value="draft">Draft</option>
          <option value="published">Published</option>
          <option value="archived">Archived</option>
        </select>
        <button className="btn sm" onClick={duplicate}>Duplicate</button>
        <button className="btn sm danger" onClick={remove}>Delete</button>
      </div>
      <h1 className="page-title">{spec.name}</h1>
      <p className="page-sub">{spec.description}</p>

      <div className="banner info">
        <span>🔒</span>
        <div>
          {gated === 0 ? "No steps pause for approval."
            : `${gated} step${gated > 1 ? "s" : ""} pause for approval.`}{" "}
          Every value below is read live from the source page or supplied as a
          run input — nothing from the demonstration is baked in.
        </div>
      </div>

      {problems.length > 0 && (
        <div className="banner error"><span>⚠</span>
          <div>This workflow can’t be saved — it would break these guarantees:
            <ul>{problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
          </div>
        </div>
      )}
      {error && <div className="banner error">{error}</div>}
      {saved && <div className="banner success">Saved as v{spec.version}.</div>}

      <div className="toolbar">
        <button className="btn sm" onClick={() => (versions ? setVersions(null) : loadVersions())}>
          {versions ? "Hide history" : `Version history (v${spec.version})`}
        </button>
        <div className="grow" />
        <button className="btn primary" disabled={!dirty || saving} onClick={save}>
          {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
        </button>
      </div>

      {versions && (
        <div className="card" style={{ marginBottom: 18 }}>
          {versions.map((v) => (
            <div className="row" key={v.version}>
              <div className="grow">
                <div className="title">v{v.version} — {v.name}</div>
                <div className="meta">{v.steps} steps · {new Date(v.created_at).toLocaleString()}</div>
              </div>
              {v.version !== spec.version && (
                <button className="btn sm" onClick={() => rollback(v.version)}>Roll back to this</button>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="card">
        {spec.steps.map((s, i) => (
          <StepCard key={s.id} step={s} index={i}
                    onIntent={(v) => edit((n) => { n.steps[i].intent = v; })}
                    onGate={(v) => edit((n) => { n.steps[i].requires_approval = v; })} />
        ))}
      </div>

      {/* ---- approval policy ---- */}
      <div className="section-h">Approval policy</div>
      <div className="card" style={{ padding: 18 }}>
        <div className="field">
          <label>When a gated step is reached</label>
          <select className="input" value={policy.mode}
                  onChange={(e) => edit((n) => {
                    n.approval_policy.mode = e.target.value as typeof policy.mode;
                  })}>
            <option value="always_ask">Always ask a human</option>
            <option value="auto_below_amount">Auto-approve small amounts, escalate the rest</option>
          </select>
        </div>
        {policy.mode === "auto_below_amount" && (
          <div className="field">
            <label>Auto-approve when <code>{policy.amount_key}</code> is below</label>
            <input className="input mono" type="number"
                   value={policy.auto_approve_below ?? ""}
                   placeholder="e.g. 5000"
                   onChange={(e) => edit((n) => {
                     n.approval_policy.auto_approve_below =
                       e.target.value === "" ? null : Number(e.target.value);
                   })} />
            <p className="meta" style={{ marginBottom: 0 }}>
              Bills under this post automatically (logged as <code>policy</code>);
              anything at/above, or that can’t be read as a number, waits for you.
            </p>
          </div>
        )}
      </div>

      {/* ---- run ---- */}
      <div className="section-h">Run this workflow</div>
      <div className="card" style={{ padding: 18 }}>
        {spec.parameters.length === 0 && (
          <p className="meta" style={{ marginTop: 0 }}>This workflow needs no inputs.</p>
        )}
        {spec.parameters.map((p) => (
          <div className="field" key={p.key}>
            <label>{p.key} <span className="hint">— {p.description}</span></label>
            <input className="input mono" value={params[p.key] ?? ""}
                   placeholder={p.example ?? ""}
                   onChange={(e) => setParams({ ...params, [p.key]: e.target.value })} />
          </div>
        ))}
        <button className="btn primary big" disabled={starting} onClick={run}>
          {starting ? "Starting…" : "Run once"}
        </button>
        {dirty && <span className="meta" style={{ marginLeft: 12 }}>
          Unsaved edits won’t affect this run until you save.</span>}
      </div>

      {/* ---- batch ---- */}
      {spec.parameters.length > 0 && (
        <>
          <div className="section-h">Run a batch</div>
          <div className="card" style={{ padding: 18 }}>
            <div className="field">
              <label>{spec.parameters[0].key} values
                <span className="hint"> — one per line (or comma-separated)</span>
              </label>
              <textarea className="input mono" rows={4} value={batchText}
                        placeholder={"INV-1002\nINV-1003\nINV-1004"}
                        onChange={(e) => setBatchText(e.target.value)} />
            </div>
            <button className="btn big" disabled={starting} onClick={runBatch}>
              Run batch under policy
            </button>
            <p className="meta" style={{ marginBottom: 0 }}>
              Each value becomes its own governed run. The worker pool throttles
              how many execute at once; small ones can auto-post under your policy.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
