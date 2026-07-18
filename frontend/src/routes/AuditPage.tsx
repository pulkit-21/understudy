import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { SkeletonList } from "../components/Skeleton";

function when(ts: string) {
  try { return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
  catch { return ts; }
}

export function AuditPage() {
  const nav = useNavigate();
  const { data, error, loading } = useAsync(() => api.auditLog(), []);
  const events = data?.events ?? null;
  const [q, setQ] = useState("");

  const shown = useMemo(() => {
    if (!events) return [];
    const t = q.toLowerCase();
    return t ? events.filter((e) =>
      `${e.kind} ${e.detail} ${e.actor} ${e.run_id}`.toLowerCase().includes(t)) : events;
  }, [events, q]);

  return (
    <div className="container">
      <h1 className="page-title">Audit log</h1>
      <p className="page-sub">
        Every action across the workspace — who did what and when. Approvals are
        attributed to a human; automated steps to the agent or policy.
      </p>
      {error && <div className="banner error">{error}</div>}

      <div className="toolbar">
        <input className="input" placeholder="Filter by kind, actor, detail, run…"
               value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {loading ? <SkeletonList rows={6} />
        : shown.length === 0 ? <div className="card empty">No audit events yet.</div>
        : (
          <div className="card log">
            {shown.map((e, i) => (
              <div className={"logline k-" + e.kind} key={i}>
                <span className="t">{when(e.ts)}</span>
                <span className={"who " + e.actor}>{e.actor}</span>
                <span className="kind">{e.kind}</span>
                <span className="msg">{e.detail}</span>
                <a className="meta" style={{ fontFamily: "var(--mono)", cursor: "pointer" }}
                   onClick={() => nav(`/runs/${e.run_id}`)}>{e.run_id}</a>
              </div>
            ))}
          </div>
        )}
    </div>
  );
}
