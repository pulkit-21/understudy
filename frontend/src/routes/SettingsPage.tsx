import { useEffect, useState } from "react";
import { api, ApiError, AuthUser, UsageEntry } from "../lib/api";
import { useAuth } from "../lib/auth";

export function SettingsPage() {
  const { user, logout } = useAuth();
  const [usage, setUsage] = useState<{ total_usd: number; entries: UsageEntry[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.usage()
      .then(setUsage)
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, []);

  const u = user as AuthUser;

  return (
    <div className="container">
      <h1 className="page-title">Settings</h1>
      <p className="page-sub">Your workspace and usage.</p>
      {error && <div className="banner error">{error}</div>}

      <div className="section-h">Account</div>
      <div className="card" style={{ padding: 18 }}>
        <div className="kv"><span>Signed in as</span><b>{u?.email}</b></div>
        <div className="kv"><span>Name</span><b>{u?.name || "—"}</b></div>
        <div className="kv"><span>Workspace</span><b style={{ fontFamily: "var(--mono)" }}>{u?.org_id}</b></div>
        <button className="btn danger sm" style={{ marginTop: 12 }} onClick={logout}>Sign out</button>
      </div>

      <div className="section-h">LLM usage &amp; cost</div>
      <div className="card" style={{ padding: 18 }}>
        <p className="meta" style={{ marginTop: 0 }}>
          The model is used only to make a learned workflow readable — once per
          workflow. Runs are deterministic and cost nothing.
        </p>
        <div className="stat-value" style={{ fontSize: 24 }}>
          ${(usage?.total_usd ?? 0).toFixed(4)}
        </div>
        <div className="stat-label">total, this workspace</div>
      </div>

      {usage && usage.entries.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          {usage.entries.map((e, i) => (
            <div className="row" key={i}>
              <div className="grow">
                <div className="title">{e.kind} · <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>{e.model}</span></div>
                <div className="meta">
                  {e.input_tokens.toLocaleString()} in / {e.output_tokens.toLocaleString()} out ·
                  {" "}{new Date(e.created_at).toLocaleString()}
                </div>
              </div>
              <b>${e.cost_usd.toFixed(4)}</b>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
