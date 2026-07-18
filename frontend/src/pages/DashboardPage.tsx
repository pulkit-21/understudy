import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, DashboardData } from "../api";
import { Icon } from "../Icon";

function Stat({ label, value, hint, accent, icon }: {
  label: string; value: string; hint?: string; accent?: string; icon: string;
}) {
  return (
    <div className="stat card">
      <div className="stat-top">
        <span className="stat-ic"
              style={accent ? { background: "transparent", color: accent } : undefined}>
          <Icon name={icon} size={17} />
        </span>
      </div>
      <div className="stat-value" style={accent ? { color: accent } : undefined}>
        {value}
      </div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

// Status is a *state* job, so it uses the reserved status palette (never the
// categorical hues) and always ships with a label — identity is never by color
// alone. Order runs left→right along their lifecycle.
const STATUS_META: { key: string; label: string; color: string }[] = [
  { key: "running", label: "Running", color: "var(--primary)" },
  { key: "awaiting_approval", label: "Awaiting approval", color: "var(--warn)" },
  { key: "completed", label: "Completed", color: "var(--success)" },
  { key: "rejected", label: "Rejected", color: "#7c8698" },
  { key: "failed", label: "Failed", color: "var(--danger)" },
];

function RunsByOutcome({ counts, total, onPick }: {
  counts: Record<string, number>; total: number; onPick: (status: string) => void;
}) {
  const present = STATUS_META.filter((s) => (counts[s.key] ?? 0) > 0);
  return (
    <div className="card viz">
      <div className="viz-head">
        <span>Runs by outcome</span>
        <span className="viz-total">{total} total</span>
      </div>
      <div className="stackbar" role="img"
           aria-label={"Runs by outcome: " + present.map((s) => `${counts[s.key]} ${s.label}`).join(", ")}>
        {present.map((s) => (
          <div key={s.key} className="stackbar-seg"
               style={{ flexGrow: counts[s.key], background: s.color }}
               title={`${s.label}: ${counts[s.key]}`}
               onClick={() => onPick(s.key)} />
        ))}
      </div>
      <div className="viz-legend">
        {present.map((s) => (
          <button key={s.key} className="legend-item" onClick={() => onPick(s.key)}>
            <span className="legend-dot" style={{ background: s.color }} />
            <span className="legend-label">{s.label}</span>
            <span className="legend-val">{counts[s.key]}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="container">
      <h1 className="page-title">Dashboard</h1>
      <p className="page-sub">Your team's workflow automation at a glance.</p>
      <div className="stat-grid">
        {Array.from({ length: 6 }).map((_, i) => (
          <div className="stat card" key={i}>
            <div className="skeleton" style={{ width: 30, height: 30, borderRadius: 8 }} />
            <div className="skeleton skeleton-row" style={{ width: "50%", height: 26, marginTop: 12 }} />
            <div className="skeleton skeleton-row" style={{ width: "70%" }} />
          </div>
        ))}
      </div>
      <div className="section-h">Recent runs</div>
      <div className="card" style={{ padding: 18 }}>
        {Array.from({ length: 3 }).map((_, i) => (
          <div className="skeleton skeleton-row" key={i} style={{ width: `${80 - i * 12}%`, height: 18 }} />
        ))}
      </div>
    </div>
  );
}

export function DashboardPage() {
  const nav = useNavigate();
  const [d, setD] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.dashboard()
      .then(setD)
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, []);

  if (error) return <div className="container"><div className="banner error">{error}</div></div>;
  if (!d) return <DashboardSkeleton />;

  const rate = d.success_rate === null ? "—" : `${Math.round(d.success_rate * 100)}%`;
  const hrs = (d.minutes_saved / 60);
  const saved = hrs >= 1 ? `${hrs.toFixed(1)} h` : `${d.minutes_saved} min`;

  return (
    <div className="container">
      <h1 className="page-title">Dashboard</h1>
      <p className="page-sub">Your team's workflow automation at a glance.</p>

      {d.pending_approvals > 0 && (
        <div className="banner warn" style={{ cursor: "pointer" }}
             onClick={() => nav("/runs?status=awaiting_approval")}>
          <span>⏸</span>
          <div><strong>{d.pending_approvals}</strong> run
            {d.pending_approvals > 1 ? "s" : ""} waiting for your approval —
            review {d.pending_approvals > 1 ? "them" : "it"} →</div>
        </div>
      )}

      <div className="stat-grid">
        <Stat icon="workflows" label="Workflows" value={String(d.workflows)} />
        <Stat icon="runs" label="Total runs" value={String(d.total_runs)} />
        <Stat icon="check" label="Success rate" value={rate}
              accent="var(--success)"
              hint={`${d.run_counts.completed ?? 0} completed`} />
        <Stat icon="approvals" label="Pending approvals" value={String(d.pending_approvals)}
              accent={d.pending_approvals ? "var(--warn)" : undefined} />
        <Stat icon="clock" label="Est. time saved" value={saved}
              hint="~1.5 min per posted bill" />
        <Stat icon="dollar" label="LLM cost" value={`$${d.cost_usd.toFixed(2)}`}
              hint="induction + agent; runs are free" />
      </div>

      {d.total_runs > 0 && (
        <RunsByOutcome counts={d.run_counts} total={d.total_runs}
                       onPick={(s) => nav(`/runs?status=${s}`)} />
      )}

      <div className="section-h">Recent runs</div>
      {d.recent.length === 0 ? (
        <div className="card empty">
          No runs yet. Open a <a href="/workflows"
            onClick={(e) => { e.preventDefault(); nav("/workflows"); }}>workflow</a> and run it.
        </div>
      ) : (
        <div className="card">
          {d.recent.map((r) => (
            <div className="row" key={r.id} style={{ cursor: "pointer" }}
                 onClick={() => nav(`/runs/${r.id}`)}>
              <span className={"status-pill status-" + r.status}>
                <span className="dot" />{r.status.replace("_", " ")}
              </span>
              <div className="grow">
                <div className="meta" style={{ fontFamily: "var(--mono)" }}>{r.id}</div>
                <div className="meta">
                  {Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(", ") || "no inputs"}
                  {r.batch_id ? " · batch" : ""}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
