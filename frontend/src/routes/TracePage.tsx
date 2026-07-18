import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Replayer } from "rrweb";
import "rrweb/dist/style.css";
import { api, ApiError, Trace } from "../lib/api";

function path(url: string) {
  try { return new URL(url).pathname; } catch { return url; }
}
function clock(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function TracePage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);

  const hostRef = useRef<HTMLDivElement>(null);
  const repRef = useRef<Replayer | null>(null);
  const [playing, setPlaying] = useState(false);
  const [dur, setDur] = useState(0);
  const [pos, setPos] = useState(0);

  useEffect(() => {
    api.getTrace(id)
      .then(setTrace)
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, [id]);

  // Sentry-style session replay via rrweb's Replayer + our own controls.
  useEffect(() => {
    if (!trace?.has_replay || !hostRef.current) return;
    const host = hostRef.current;
    let disposed = false;
    let timer: number | undefined;
    api.getReplay(id).then((res) => {
      const events = res.events as never[];
      if (disposed || !host || events.length < 2) return;
      host.innerHTML = "";
      const rep = new Replayer(events, {
        root: host, skipInactive: true, showWarning: false, mouseTail: false,
      });
      repRef.current = rep;
      setDur(rep.getMetaData().totalTime);
      // rrweb renders at the recorded viewport size; scale it to fit the card.
      const wrap = host.querySelector(".replayer-wrapper") as HTMLElement | null;
      if (wrap) {
        const rw = parseInt(wrap.style.width) || 1150;
        const rh = parseInt(wrap.style.height) || 950;
        const scale = Math.min(1, (host.clientWidth || 800) / rw);
        wrap.style.transform = `scale(${scale})`;
        wrap.style.transformOrigin = "top left";
        host.style.height = `${Math.round(rh * scale)}px`;
        host.style.overflow = "hidden";
      }
      timer = window.setInterval(() => {
        const t = rep.getCurrentTime();
        setPos(t);
      }, 100);
    }).catch((e) => setReplayError(e instanceof ApiError ? String(e.detail) : String(e)));
    return () => {
      disposed = true;
      if (timer) clearInterval(timer);
      try { repRef.current?.pause(); } catch { /* ignore */ }
      repRef.current = null;
      if (host) host.innerHTML = "";
    };
  }, [trace, id]);

  function toggle() {
    const rep = repRef.current; if (!rep) return;
    if (playing) { rep.pause(); setPlaying(false); }
    else { rep.play(pos >= dur ? 0 : pos); setPlaying(true); }
  }
  function seek(ms: number) {
    const rep = repRef.current; if (!rep) return;
    rep.pause(ms);  // renders the frame at this offset, paused
    setPos(ms); setPlaying(false);
  }

  if (error) return <div className="container"><div className="banner error">{error}</div></div>;
  if (!trace) return <div className="container"><div className="spinner">Loading…</div></div>;

  return (
    <div className="container">
      <div className="toolbar">
        <a href="/workflows" onClick={(e) => { e.preventDefault(); nav("/workflows"); }}>← Workflows</a>
      </div>
      <h1 className="page-title">{trace.name}</h1>
      <p className="page-sub">
        The recorded demonstration — {trace.events.length} semantic events (roles,
        labels, test-ids; never pixel coordinates). This is the raw material
        induction turns into a workflow.
      </p>

      {trace.has_replay && (
        <>
          <div className="section-h">Session replay</div>
          <div className="card" style={{ padding: 12 }}>
            <div ref={hostRef} className="replay-host" />
            {replayError
              ? <div className="banner error">{replayError}</div>
              : (
                <div className="replay-controls">
                  <button className="btn sm" onClick={toggle}>
                    {playing ? "⏸ Pause" : "▶ Play"}
                  </button>
                  <span className="replay-time">{clock(pos)}</span>
                  <input type="range" min={0} max={dur || 1} value={Math.min(pos, dur)}
                         onChange={(e) => seek(Number(e.target.value))} />
                  <span className="replay-time">{clock(dur)}</span>
                </div>
              )}
            <p className="meta" style={{ margin: "6px 4px 0" }}>
              A pixel-for-pixel playback of the demonstration (captured with rrweb).
              Scrub the timeline to see exactly what was done.
            </p>
          </div>
        </>
      )}

      <div className="section-h">Semantic events</div>
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
