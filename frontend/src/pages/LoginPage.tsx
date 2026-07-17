import { useState } from "react";
import { ApiError } from "../api";
import { useAuth } from "../auth";

const DEMO_EMAIL = "demo@understudy.app";
const DEMO_PASSWORD = "understudy";

export function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, name);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function demo() {
    setBusy(true);
    setError(null);
    try {
      await login(DEMO_EMAIL, DEMO_PASSWORD);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="authwrap">
      <div className="authcard card">
        <div className="brand" style={{ fontSize: 20, marginBottom: 4 }}>
          Understudy
        </div>
        <p className="page-sub" style={{ marginBottom: 22 }}>
          Learn a browser workflow by watching, then run it with a gate.
        </p>

        <button className="btn primary big" style={{ width: "100%" }}
                disabled={busy} onClick={demo}>
          ✨ Try the live demo
        </button>
        <div className="or">or</div>

        <form onSubmit={submit}>
          {mode === "register" && (
            <div className="field">
              <label>Name</label>
              <input className="input" value={name}
                     onChange={(e) => setName(e.target.value)} />
            </div>
          )}
          <div className="field">
            <label>Email</label>
            <input className="input" type="email" required value={email}
                   onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="field">
            <label>Password <span className="hint">(min 8 characters)</span></label>
            <input className="input" type="password" required value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <div className="banner error">{error}</div>}
          <button className="btn primary big" style={{ width: "100%" }}
                  disabled={busy} type="submit">
            {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <div className="authswitch">
          {mode === "login" ? (
            <>New here?{" "}
              <a onClick={() => { setMode("register"); setError(null); }}>
                Create an account
              </a></>
          ) : (
            <>Have an account?{" "}
              <a onClick={() => { setMode("login"); setError(null); }}>Sign in</a></>
          )}
        </div>
      </div>
    </div>
  );
}
