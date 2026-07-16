import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, WorkflowSpec, WorkflowStep } from "../api";

// Render a step's value as a chip that shows where the data comes from:
// a live extract, a run input parameter, or a literal constant.
function ValueChip({ value }: { value: string }) {
  const ex = value.match(/^\{\{\s*extract\.([\w.]+)\s*\}\}$/);
  if (ex) return <span className="chip extract">↳ read: {ex[1]}</span>;
  const pm = value.match(/^\{\{\s*([\w.]+)\s*\}\}$/);
  if (pm) return <span className="chip param">input: {pm[1]}</span>;
  return <span className="chip">"{value}"</span>;
}

function StepCard({
  step, index, onIntent, onGate,
}: {
  step: WorkflowStep;
  index: number;
  onIntent: (v: string) => void;
  onGate: (v: boolean) => void;
}) {
  const testid = step.target?.testid;
  return (
    <div className={"step" + (step.risk === "commit" ? " commit" : "")}>
      <div className="num">{index + 1}</div>
      <div className="body">
        <textarea
          className="intent"
          rows={1}
          value={step.intent}
          onChange={(e) => onIntent(e.target.value)}
        />
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
              <input
                type="checkbox"
                checked={step.requires_approval}
                onChange={(e) => onGate(e.target.checked)}
              />
              requires approval
            </label>
          )}
          {step.requires_approval && step.risk !== "commit" && (
            <span className="badge gate">gated</span>
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

  useEffect(() => {
    api.getWorkflow(id)
      .then((s) => {
        setSpec(s);
        setParams(Object.fromEntries(s.parameters.map((p) => [p.key, p.example ?? ""])));
      })
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, [id]);

  const gated = useMemo(
    () => spec?.steps.filter((s) => s.requires_approval).length ?? 0,
    [spec],
  );

  function edit(mut: (s: WorkflowSpec) => void) {
    if (!spec) return;
    const next = structuredClone(spec);
    mut(next);
    setSpec(next);
    setDirty(true);
    setSaved(false);
  }

  async function save() {
    if (!spec) return;
    setSaving(true);
    setProblems([]);
    setError(null);
    try {
      const updated = await api.saveWorkflow(id, spec);
      setSpec(updated);
      setDirty(false);
      setSaved(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && Array.isArray(e.detail)) {
        setProblems(e.detail as string[]);
      } else {
        setError(e instanceof ApiError ? String(e.detail) : String(e));
      }
    } finally {
      setSaving(false);
    }
  }

  async function run() {
    setStarting(true);
    setError(null);
    try {
      const { run_id } = await api.startRun(id, params);
      nav(`/runs/${run_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
      setStarting(false);
    }
  }

  if (error && !spec) return <div className="container"><div className="banner error">{error}</div></div>;
  if (!spec) return <div className="container"><div className="spinner">Loading…</div></div>;

  return (
    <div className="container">
      <div className="toolbar">
        <a href="/" onClick={(e) => { e.preventDefault(); nav("/"); }}>← Workflows</a>
      </div>
      <h1 className="page-title">{spec.name}</h1>
      <p className="page-sub">{spec.description}</p>

      <div className="banner info">
        <span>🔒</span>
        <div>
          {gated === 0
            ? "No steps pause for approval."
            : `${gated} step${gated > 1 ? "s" : ""} pause for human approval before running.`}{" "}
          Every value below is either read live from the source page or supplied
          as a run input — nothing from the demonstration is baked in.
        </div>
      </div>

      {problems.length > 0 && (
        <div className="banner error">
          <span>⚠</span>
          <div>
            This workflow can’t be saved — it would break these guarantees:
            <ul>{problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
          </div>
        </div>
      )}
      {error && <div className="banner error">{error}</div>}
      {saved && <div className="banner success">Saved as v{spec.version}.</div>}

      <div className="toolbar">
        <div className="grow" />
        <button className="btn primary" disabled={!dirty || saving} onClick={save}>
          {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
        </button>
      </div>

      <div className="card">
        {spec.steps.map((s, i) => (
          <StepCard
            key={s.id}
            step={s}
            index={i}
            onIntent={(v) => edit((n) => { n.steps[i].intent = v; })}
            onGate={(v) => edit((n) => { n.steps[i].requires_approval = v; })}
          />
        ))}
      </div>

      <div className="section-h">Run this workflow</div>
      <div className="card" style={{ padding: 18 }}>
        {spec.parameters.length === 0 && (
          <p className="meta" style={{ marginTop: 0 }}>This workflow needs no inputs.</p>
        )}
        {spec.parameters.map((p) => (
          <div className="field" key={p.key}>
            <label>
              {p.key} <span className="hint">— {p.description}</span>
            </label>
            <input
              className="input mono"
              value={params[p.key] ?? ""}
              placeholder={p.example ?? ""}
              onChange={(e) => setParams({ ...params, [p.key]: e.target.value })}
            />
          </div>
        ))}
        <button className="btn primary big" disabled={starting} onClick={run}>
          {starting ? "Starting…" : "Run workflow"}
        </button>
        {dirty && (
          <span className="meta" style={{ marginLeft: 12 }}>
            Unsaved edits won’t affect this run until you save.
          </span>
        )}
      </div>
    </div>
  );
}
