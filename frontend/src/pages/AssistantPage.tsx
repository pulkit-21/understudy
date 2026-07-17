import { useEffect, useRef, useState } from "react";
import { AgentStep, api, ApiError } from "../api";
import { Icon } from "../Icon";

interface Msg { role: "user" | "assistant"; content: string; steps?: AgentStep[]; }

const SUGGESTIONS = [
  "What workflows do I have?",
  "Run the invoice workflow on INV-1002",
  "Post invoices INV-1003, INV-1004 and INV-1006",
  "Which runs are waiting for my approval?",
];

function summarize(v: Record<string, unknown>): string {
  const s = JSON.stringify(v);
  return s.length > 140 ? s.slice(0, 140) + "…" : s;
}

function Activity({ steps }: { steps: AgentStep[] }) {
  if (!steps?.length) return null;
  return (
    <details className="activity">
      <summary><Icon name="tool" size={13} /> {steps.length} action{steps.length > 1 ? "s" : ""} taken</summary>
      {steps.map((s, i) => (
        <div className="actrow" key={i}>
          <span className="acttool">{s.tool}</span>
          {Object.keys(s.input || {}).length > 0 && (
            <code className="actio">{summarize(s.input)}</code>
          )}
          <span className="actarrow">→</span>
          <code className="actio">{summarize(s.result)}</code>
        </div>
      ))}
    </details>
  );
}

export function AssistantPage() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    const next: Msg[] = [...msgs, { role: "user", content: q }];
    setMsgs(next);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const res = await api.chat(next.map((m) => ({ role: m.role, content: m.content })));
      setMsgs((m) => [...m, { role: "assistant", content: res.reply, steps: res.steps }]);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container chat-container">
      <h1 className="page-title">Assistant</h1>
      <p className="page-sub">
        Ask in plain language — the assistant discovers, learns, and runs your
        workflows using the same tools and guardrails. It can start runs, but it
        can never approve an irreversible step; those still wait for you in
        Approvals.
      </p>

      <div className="chat-thread">
        {msgs.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-ic"><Icon name="chat" size={26} /></div>
            <p>Try one of these:</p>
            <div className="chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn sm" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div className={"msg " + m.role} key={i}>
            <div className="msg-bubble">
              {m.content.split("\n").map((line, j) => <div key={j}>{line || " "}</div>)}
            </div>
            {m.role === "assistant" && m.steps && <Activity steps={m.steps} />}
          </div>
        ))}
        {busy && <div className="msg assistant"><div className="msg-bubble typing">Working…</div></div>}
        {error && <div className="banner error">{error}</div>}
        <div ref={endRef} />
      </div>

      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <input className="input" placeholder="Message the assistant…" value={input}
               disabled={busy} onChange={(e) => setInput(e.target.value)} />
        <button className="btn primary" type="submit" disabled={busy || !input.trim()}>
          <Icon name="send" size={16} />
        </button>
      </form>
    </div>
  );
}
