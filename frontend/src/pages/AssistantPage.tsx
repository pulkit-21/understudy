import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AgentCard, AgentStep, api, ApiError } from "../api";
import { Icon } from "../Icon";

interface Msg {
  role: "user" | "assistant";
  content: string;
  steps?: AgentStep[];
  cards?: AgentCard[];
}

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
          {Object.keys(s.input || {}).length > 0 && <code className="actio">{summarize(s.input)}</code>}
          <span>→</span>
          <code className="actio">{summarize(s.result)}</code>
        </div>
      ))}
    </details>
  );
}

// A run the agent touched — the human can approve/reject inline (the agent
// itself can't, by design).
function RunCard({ card }: { card: AgentCard }) {
  const nav = useNavigate();
  const [status, setStatus] = useState(card.status);
  const [busy, setBusy] = useState(false);

  async function act(kind: "approve" | "reject") {
    setBusy(true);
    try {
      await (kind === "approve" ? api.approve(card.id) : api.reject(card.id));
      setStatus(kind === "approve" ? "running" : "rejected");
      setTimeout(async () => {
        try { setStatus((await api.getRun(card.id)).status); } catch { /* ignore */ }
        setBusy(false);
      }, 1500);
    } catch { setBusy(false); }
  }

  return (
    <div className="agent-card">
      <span className={"status-pill status-" + status}>
        <span className="dot" />{status?.replace("_", " ")}
      </span>
      <div className="grow" style={{ cursor: "pointer" }} onClick={() => nav(`/runs/${card.id}`)}>
        <div className="ac-title">{card.id}</div>
        <div className="meta">
          {Object.entries(card.params || {}).map(([k, v]) => `${k}=${v}`).join(", ") || "run"}
        </div>
      </div>
      {status === "awaiting_approval" && (
        <>
          <button className="btn sm success" disabled={busy} onClick={() => act("approve")}>Approve</button>
          <button className="btn sm danger" disabled={busy} onClick={() => act("reject")}>Reject</button>
        </>
      )}
      <button className="btn sm" onClick={() => nav(`/runs/${card.id}`)}>View</button>
    </div>
  );
}

function Cards({ cards }: { cards: AgentCard[] }) {
  const nav = useNavigate();
  if (!cards?.length) return null;
  return (
    <div className="agent-cards">
      {cards.map((c) => c.type === "run"
        ? <RunCard card={c} key={c.id} />
        : (
          <div className="agent-card" key={c.id}>
            <span className="ac-ic"><Icon name="workflows" size={15} /></span>
            <div className="grow"><div className="ac-title">{c.name}</div>
              <div className="meta">{(c.param_keys ?? []).length ? `input: ${(c.param_keys ?? []).join(", ")}` : "no inputs"}</div>
            </div>
            <button className="btn sm" onClick={() => nav(`/workflows/${c.id}`)}>Open</button>
          </div>
        ))}
    </div>
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
      setMsgs((m) => [...m, { role: "assistant", content: res.reply, steps: res.steps, cards: res.cards }]);
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
        can never approve an irreversible step; those still wait for you (approve
        them right here on the run card, or in Approvals).
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
              {m.content.split("\n").map((line, j) => <div key={j}>{line || " "}</div>)}
            </div>
            {m.role === "assistant" && m.cards && <Cards cards={m.cards} />}
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
