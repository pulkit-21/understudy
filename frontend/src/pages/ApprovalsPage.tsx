import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, RunSummary } from "../api";
import { SkeletonList } from "../Skeleton";

export function ApprovalsPage() {
  const nav = useNavigate();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState<string | null>(null);

  const load = useCallback(() => {
    api.listRuns({ status: "awaiting_approval" })
      .then(setRuns)
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  async function decide(id: string, kind: "approve" | "reject") {
    setActing(id);
    setError(null);
    // Optimistic: drop the row immediately so the queue feels instant. Restore
    // it (via reload) only if the call fails.
    const before = runs;
    setRuns((rs) => (rs ? rs.filter((r) => r.id !== id) : rs));
    try {
      await (kind === "approve" ? api.approve(id) : api.reject(id));
      setTimeout(load, 400);  // reconcile with server truth once the run settles
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
      setRuns(before);        // rollback the optimistic removal
    } finally {
      setActing(null);
    }
  }

  return (
    <div className="container">
      <h1 className="page-title">Approvals</h1>
      <p className="page-sub">
        Runs paused at a gate, waiting for a human. This is the queue that needs
        you — everything else is running or done.
      </p>
      {error && <div className="banner error">{error}</div>}

      {runs === null ? (
        <SkeletonList rows={3} />
      ) : runs.length === 0 ? (
        <div className="card empty">🎉 Nothing waiting. All caught up.</div>
      ) : (
        <div className="card">
          {runs.map((r) => (
            <div className="row" key={r.id}>
              <div className="grow">
                <div className="title" style={{ fontFamily: "var(--mono)", fontSize: 13 }}>
                  <a href={`/runs/${r.id}`}
                     onClick={(e) => { e.preventDefault(); nav(`/runs/${r.id}`); }}>
                    {r.id}
                  </a>
                </div>
                <div className="meta">
                  {Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(", ")}
                  {r.batch_id ? " · batch" : ""}
                </div>
              </div>
              <button className="btn sm success" disabled={acting === r.id}
                      onClick={() => decide(r.id, "approve")}>Approve</button>
              <button className="btn sm danger" disabled={acting === r.id}
                      onClick={() => decide(r.id, "reject")}>Reject</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
