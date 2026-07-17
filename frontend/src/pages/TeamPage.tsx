import { useEffect, useState } from "react";
import { api, ApiError, TeamMember } from "../api";

function initials(name: string, email: string) {
  const n = (name || email || "?").trim();
  return n.slice(0, 2).toUpperCase();
}

export function TeamPage() {
  const [members, setMembers] = useState<TeamMember[] | null>(null);
  const [me, setMe] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.team()
      .then((d) => { setMembers(d.members); setMe(d.me); })
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, []);

  return (
    <div className="container">
      <h1 className="page-title">Team</h1>
      <p className="page-sub">
        Everyone in this workspace. Workflows, runs, and the audit trail are
        shared across the team and isolated from other organizations.
      </p>
      {error && <div className="banner error">{error}</div>}

      <div className="toolbar">
        <div className="grow" />
        <button className="btn" title="Invite is stubbed in the demo"
                onClick={() => alert("Invites are stubbed in the demo — every member shares this org's data.")}>
          + Invite member
        </button>
      </div>

      {members === null ? <div className="spinner">Loading…</div> : (
        <div className="card">
          {members.map((m) => (
            <div className="row" key={m.id}>
              <span className="avatar">{initials(m.name, m.email)}</span>
              <div className="grow">
                <div className="title">{m.name || m.email}{m.id === me && <span className="badge gate" style={{ marginLeft: 8 }}>you</span>}</div>
                <div className="meta">{m.email} · joined {new Date(m.created_at).toLocaleDateString()}</div>
              </div>
              <span className="badge read">admin</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
