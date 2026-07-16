import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, RunSummary } from "../api";

function when(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function RunsPage() {
  const nav = useNavigate();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listRuns()
      .then(setRuns)
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, []);

  return (
    <div className="container">
      <h1 className="page-title">Runs</h1>
      <p className="page-sub">
        Every execution of a workflow, newest first — its status, inputs, and a
        full audit trail. Runs persist across restarts.
      </p>

      {error && <div className="banner error">{error}</div>}

      {runs === null ? (
        <div className="spinner">Loading…</div>
      ) : runs.length === 0 ? (
        <div className="card empty">
          No runs yet. Open a workflow and run it to see it here.
        </div>
      ) : (
        <div className="card">
          {runs.map((r) => (
            <div className="row" key={r.id} style={{ cursor: "pointer" }}
                 onClick={() => nav(`/runs/${r.id}`)}>
              <span className={"status-pill status-" + r.status}>
                <span className="dot" />
                {r.status.replace("_", " ")}
              </span>
              <div className="grow">
                <div className="title" style={{ fontFamily: "var(--mono)", fontSize: 13 }}>
                  {r.id}
                </div>
                <div className="meta">
                  {Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(", ") || "no inputs"}
                  {" · "}{r.steps} events · {when(r.created_at)}
                </div>
              </div>
              <button className="btn sm" onClick={(e) => { e.stopPropagation(); nav(`/runs/${r.id}`); }}>
                View
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
