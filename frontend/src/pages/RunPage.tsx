import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, Run, RunEvent, RunStatus } from "../api";

const KIND_TO_STATUS: Record<string, RunStatus> = {
  awaiting_approval: "awaiting_approval",
  approved: "running",
  run_done: "completed",
  run_failed: "failed",
  rejected: "rejected",
};

function hhmmss(ts: string) {
  return new Date(ts).toLocaleTimeString([], { hour12: false });
}

export function RunPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [run, setRun] = useState<Run | null>(null);
  const [status, setStatus] = useState<RunStatus>("running");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [extracts, setExtracts] = useState<Record<string, string>>({});
  const [frame, setFrame] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logEnd = useRef<HTMLDivElement>(null);

  // Snapshot for params / workflow link / initial status.
  useEffect(() => {
    api.getRun(id)
      .then((r) => { setRun(r); setStatus(r.status); setExtracts(r.extracts); })
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, [id]);

  // Live audit log via SSE (the backend replays history, then streams live).
  useEffect(() => {
    const es = new EventSource(api.runEventsUrl(id));
    setEvents([]);
    es.onmessage = (m) => {
      const evt = JSON.parse(m.data);
      if (evt.kind === "stream_end") { es.close(); return; }
      if (evt.kind === "frame") { setFrame(evt.detail); return; }  // live view, not logged
      setEvents((prev) => [...prev, evt as RunEvent]);
      if (KIND_TO_STATUS[evt.kind]) setStatus(KIND_TO_STATUS[evt.kind]);
      if (evt.kind === "extracted") {
        const m2 = /^(\w+) = (.*)$/.exec(evt.detail);
        if (m2) setExtracts((p) => ({ ...p, [m2[1]]: m2[2].replace(/^'|'$/g, "") }));
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [id]);

  useEffect(() => { logEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [events]);

  async function decide(kind: "approve" | "reject") {
    setActing(true);
    setError(null);
    try {
      await (kind === "approve" ? api.approve(id) : api.reject(id));
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setActing(false);
    }
  }

  const awaiting = status === "awaiting_approval";
  const terminal = ["completed", "failed", "rejected"].includes(status);
  const gateStep = [...events].reverse().find((e) => e.kind === "awaiting_approval");

  async function retry() {
    setActing(true);
    setError(null);
    try {
      const { run_id } = await api.retryRun(id);
      nav(`/runs/${run_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
      setActing(false);
    }
  }

  return (
    <div className="container">
      <div className="toolbar">
        {run && (
          <a href={`/workflows/${run.workflow_id}`}
             onClick={(e) => { e.preventDefault(); nav(`/workflows/${run.workflow_id}`); }}>
            ← Workflow
          </a>
        )}
        <div className="grow" />
        {terminal && (
          <button className="btn sm" disabled={acting} onClick={retry}>
            ↻ Run again
          </button>
        )}
        <span className={"status-pill status-" + status}>
          <span className="dot" />
          {status.replace("_", " ")}
        </span>
      </div>

      <h1 className="page-title">Run {id}</h1>
      <p className="page-sub">
        {run && Object.keys(run.params).length > 0
          ? Object.entries(run.params).map(([k, v]) => `${k} = ${v}`).join(", ")
          : "no inputs"}
      </p>

      {error && <div className="banner error">{error}</div>}

      {awaiting && (
        <div className="gatebar">
          <div className="g-title">⏸ Waiting for your approval</div>
          <div>{gateStep?.detail ?? "This step commits state and cannot be undone."}</div>
          <div className="g-actions">
            <button className="btn success big" disabled={acting}
                    onClick={() => decide("approve")}>
              Approve &amp; post
            </button>
            <button className="btn danger big" disabled={acting}
                    onClick={() => decide("reject")}>
              Reject
            </button>
          </div>
        </div>
      )}

      {status === "completed" && (
        <div className="banner success">
          <span>✓</span>
          <div>
            Workflow completed and the bill was posted.{" "}
            <a href="/erp" target="_blank" rel="noreferrer">View it in LedgerOne ↗</a>
          </div>
        </div>
      )}
      {status === "rejected" && (
        <div className="banner warn">Run rejected at the approval gate — nothing was posted.</div>
      )}

      {frame && (
        <>
          <div className="section-h">
            Live view {status === "running" && <span className="livedot" />}
          </div>
          <div className="card" style={{ padding: 8, overflow: "hidden" }}>
            <img src={`data:image/jpeg;base64,${frame}`} alt="agent browser"
                 style={{ width: "100%", borderRadius: 6, display: "block" }} />
          </div>
        </>
      )}

      {Object.keys(extracts).length > 0 && (
        <>
          <div className="section-h">Read live from the source page</div>
          <div className="card chips" style={{ padding: "12px 16px" }}>
            {Object.entries(extracts).map(([k, v]) => (
              <span className="chip extract" key={k}>{k}: {v}</span>
            ))}
          </div>
        </>
      )}

      <div className="section-h">Audit log</div>
      <div className="card log">
        {events.length === 0 && <div className="logline"><span className="msg">Connecting…</span></div>}
        {events.map((e, i) => (
          <div className={"logline k-" + e.kind} key={i}>
            <span className="t">{hhmmss(e.ts)}</span>
            <span className={"who " + e.actor}>{e.actor}</span>
            <span className="kind">{e.kind}</span>
            <span className="msg">{e.detail}</span>
          </div>
        ))}
        <div ref={logEnd} />
      </div>
    </div>
  );
}
