import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { SkeletonList } from "../components/Skeleton";

function when(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function RunsPage() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const batch = sp.get("batch") ?? undefined;
  const status = sp.get("status") ?? undefined;
  const { data, error, loading } = useAsync(
    () => api.listRuns({ batch_id: batch, status }), [batch, status]);
  const runs = data ?? [];
  const filtered = batch || status;

  return (
    <div className="container">
      <h1 className="page-title">Runs</h1>
      <p className="page-sub">
        {batch ? `Batch ${batch} — each value ran as its own governed run.`
          : status ? `Runs with status "${status.replace("_", " ")}".`
          : "Every execution of a workflow, newest first — status, inputs, and a full audit trail. Runs persist across restarts."}
        {filtered && <> <a href="/runs" onClick={(e) => { e.preventDefault(); nav("/runs"); }}>Show all →</a></>}
      </p>

      {error && <div className="banner error">{error}</div>}

      {loading ? (
        <SkeletonList rows={5} />
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
