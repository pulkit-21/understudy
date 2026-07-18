import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import { SkeletonList } from "../Skeleton";

function initials(name: string, email: string) {
  const n = (name || email || "?").trim();
  return n.slice(0, 2).toUpperCase();
}

export function TeamPage() {
  const { data, error, loading } = useAsync(() => api.team(), []);
  const members = data?.members ?? [];
  const me = data?.me ?? "";

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

      {loading ? <SkeletonList rows={3} /> : (
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
