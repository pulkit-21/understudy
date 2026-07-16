import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, Trace } from "../api";

function path(url: string) {
  try { return new URL(url).pathname; } catch { return url; }
}

export function TracePage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getTrace(id)
      .then(setTrace)
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, [id]);

  if (error) return <div className="container"><div className="banner error">{error}</div></div>;
  if (!trace) return <div className="container"><div className="spinner">Loading…</div></div>;

  return (
    <div className="container">
      <div className="toolbar">
        <a href="/" onClick={(e) => { e.preventDefault(); nav("/"); }}>← Workflows</a>
      </div>
      <h1 className="page-title">{trace.name}</h1>
      <p className="page-sub">
        The recorded demonstration — {trace.events.length} semantic events (roles,
        labels, test-ids; never pixel coordinates). This is the raw material
        induction turns into a workflow.
      </p>

      <div className="card">
        {trace.events.map((e, i) => (
          <div className="step" key={i}>
            <div className="num">{i + 1}</div>
            <div className="body">
              <div className="intent" style={{ cursor: "default" }}>
                {e.target?.name
                  ? `${e.type} — ${e.target.role ?? "element"} “${e.target.name}”`
                  : e.type}
              </div>
              <div className="detail">
                <span className="badge action">{e.type}</span>
                <span className="chip">{path(e.url)}</span>
                {e.target?.testid && <span className="chip">#{e.target.testid}</span>}
                {e.value && <span className="chip">"{e.value}"</span>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
