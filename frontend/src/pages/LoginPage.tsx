import { useState } from "react";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { Icon } from "../Icon";

const DEMO_EMAIL = "demo@understudy.app";
const DEMO_PASSWORD = "understudy";

const PROPS = [
  { icon: "record", title: "Teach it once, by doing",
    body: "Record a task in the browser — Understudy learns the procedure, not the pixels." },
  { icon: "workflows", title: "Self-healing replay",
    body: "Runs on new data; resolves each element by role, name, or test-id when the page changes." },
  { icon: "approvals", title: "Human-gated, fully audited",
    body: "Irreversible steps pause for approval. Every action is logged with actor and timestamp." },
];

export function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); }
    catch (err) { setError(err instanceof ApiError ? String(err.detail) : String(err)); }
    finally { setBusy(false); }
  }

  return (
    <div className="login-split">
      <div className="login-left">
        <div className="login-brand"><span className="logo">U</span> Understudy</div>
        <div className="login-hero">
          <h1>Browser work,<br />on autopilot.</h1>
          <p>Understudy watches you do a task once, learns the procedure, and runs
             it on new data — pausing for your approval before anything irreversible.</p>
          <div className="login-props">
            {PROPS.map((p) => (
              <div className="login-prop" key={p.title}>
                <span className="lp-ic"><Icon name={p.icon} size={17} /></span>
                <div><b>{p.title}</b><span>{p.body}</span></div>
              </div>
            ))}
          </div>
        </div>
        <div className="login-trust">
          Deterministic replay · Human approval gate · Full audit trail
        </div>
      </div>

      <div className="login-right">
        <div className="login-card">
          <h2>{mode === "login" ? "Welcome back" : "Create your workspace"}</h2>
          <p className="page-sub" style={{ marginBottom: 20 }}>
            {mode === "login" ? "Sign in to your Understudy workspace."
              : "Start a fresh, isolated workspace."}
          </p>

          <button className="btn primary big" style={{ width: "100%" }} disabled={busy}
                  onClick={() => run(() => login(DEMO_EMAIL, DEMO_PASSWORD))}>
            ✨ Try the live demo
          </button>
          <div className="or">or</div>

          <form onSubmit={(e) => {
            e.preventDefault();
            run(() => mode === "login" ? login(email, password) : register(email, password, name));
          }}>
            {mode === "register" && (
              <div className="field"><label>Name</label>
                <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
            )}
            <div className="field"><label>Email</label>
              <input className="input" type="email" required value={email}
                     onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="field"><label>Password <span className="hint">(min 8 characters)</span></label>
              <input className="input" type="password" required value={password}
                     onChange={(e) => setPassword(e.target.value)} />
            </div>
            {error && <div className="banner error">{error}</div>}
            <button className="btn primary big" style={{ width: "100%" }} disabled={busy} type="submit">
              {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <div className="authswitch">
            {mode === "login" ? (
              <>New here? <a onClick={() => { setMode("register"); setError(null); }}>Create an account</a></>
            ) : (
              <>Have an account? <a onClick={() => { setMode("login"); setError(null); }}>Sign in</a></>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
