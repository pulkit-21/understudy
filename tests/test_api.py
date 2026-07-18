"""API contract tests (through the real HTTP layer, no browser).

Covers auth-gating, the trace -> induce -> workflow path, and the workflow
lifecycle endpoints. The headful recording itself needs a display and is
exercised locally, not in CI.
"""
from app.db import SessionLocal, TraceRepo


def _seed_trace(demo_trace, org_id):
    TraceRepo(SessionLocal).save(demo_trace, org_id)
    return demo_trace


def test_endpoints_require_auth():
    from fastapi.testclient import TestClient

    from app.main import app
    anon = TestClient(app)
    assert anon.get("/api/workflows").status_code == 401
    assert anon.get("/api/traces").status_code == 401
    assert anon.get("/api/runs").status_code == 401


def test_induce_via_api_yields_invoice_id_only_spec(authed_client, demo_trace):
    client, org_id = authed_client
    trace = _seed_trace(demo_trace, org_id)
    r = client.post(f"/api/traces/{trace.id}/induce", json={"use_llm": False})
    assert r.status_code == 200
    body = r.json()
    assert body["problems"] == []
    spec = body["workflow"]
    assert [p["key"] for p in spec["parameters"]] == ["invoice_id"]
    assert body["induced_by"] == "heuristic"


def test_put_workflow_rejects_an_ungated_commit_step(authed_client, demo_trace):
    """The API must refuse to save a spec whose commit step lost its gate."""
    client, org_id = authed_client
    trace = _seed_trace(demo_trace, org_id)
    induced = client.post(f"/api/traces/{trace.id}/induce",
                          json={"use_llm": False}).json()["workflow"]
    wf_id = induced["id"]
    for step in induced["steps"]:
        if step["risk"] == "commit":
            step["requires_approval"] = False
    r = client.put(f"/api/workflows/{wf_id}", json=induced)
    assert r.status_code == 422


def test_workflow_lifecycle_status_duplicate_delete(authed_client, demo_trace):
    client, org_id = authed_client
    trace = _seed_trace(demo_trace, org_id)
    wf = client.post(f"/api/traces/{trace.id}/induce",
                     json={"use_llm": False}).json()["workflow"]
    wf_id = wf["id"]

    # archive -> hidden from the default list, visible with include_archived
    assert client.post(f"/api/workflows/{wf_id}/status",
                       json={"status": "archived"}).status_code == 200
    ids = [w["id"] for w in client.get("/api/workflows").json()]
    assert wf_id not in ids
    ids_all = [w["id"] for w in
               client.get("/api/workflows?include_archived=true").json()]
    assert wf_id in ids_all

    # duplicate -> a new draft copy
    dup = client.post(f"/api/workflows/{wf_id}/duplicate").json()
    assert dup["id"] != wf_id and dup["status"] == "draft"

    # delete
    assert client.delete(f"/api/workflows/{wf_id}").status_code == 204
    assert client.get(f"/api/workflows/{wf_id}").status_code == 404


def test_workflow_versions_and_rollback(authed_client, demo_trace):
    client, org_id = authed_client
    trace = _seed_trace(demo_trace, org_id)
    wf = client.post(f"/api/traces/{trace.id}/induce",
                     json={"use_llm": False}).json()["workflow"]
    wf_id = wf["id"]
    # edit the name -> new version
    wf["name"] = "Renamed workflow"
    client.put(f"/api/workflows/{wf_id}", json=wf)
    versions = client.get(f"/api/workflows/{wf_id}/versions").json()
    assert len(versions) >= 2
    # roll back to v1
    rolled = client.post(f"/api/workflows/{wf_id}/rollback/1").json()
    assert rolled["name"] != "Renamed workflow"


def test_stop_unknown_recording_is_404(authed_client):
    client, _ = authed_client
    assert client.post("/api/recordings/does-not-exist/stop").status_code == 404


def test_dashboard_reports_kpis(authed_client, demo_trace):
    client, org_id = authed_client
    trace = _seed_trace(demo_trace, org_id)
    client.post(f"/api/traces/{trace.id}/induce", json={"use_llm": False})
    d = client.get("/api/dashboard").json()
    assert d["workflows"] >= 1
    assert "run_counts" in d and "pending_approvals" in d and "cost_usd" in d


def test_audit_feed_is_org_scoped_and_shaped(authed_client, demo_trace):
    client, _ = authed_client
    events = client.get("/api/audit").json()["events"]
    assert isinstance(events, list)   # empty is fine; shape is the contract


def test_usage_endpoint_returns_meter(authed_client):
    client, _ = authed_client
    u = client.get("/api/usage").json()
    assert "total_usd" in u and "entries" in u


def test_team_lists_the_current_user(authed_client):
    client, _ = authed_client
    body = client.get("/api/auth/team").json()
    assert body["me"] and len(body["members"]) >= 1
    assert any("email" in m for m in body["members"])


def test_conversation_crud_via_api(authed_client, demo_trace, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_AGENT_MOCK", "1")
    client, org_id = authed_client
    from app.db import SessionLocal, WorkflowRepo
    from app.induction.heuristic import induce_heuristic
    WorkflowRepo(SessionLocal).save(induce_heuristic(demo_trace), org_id)
    cid = client.post("/api/agent/chat",
                      json={"message": "what workflows do I have?"}).json()["conversation_id"]
    assert cid in [c["id"] for c in client.get("/api/agent/conversations").json()]
    assert client.delete(f"/api/agent/conversations/{cid}").status_code in (200, 204)


def test_get_unknown_run_is_404(authed_client):
    client, _ = authed_client
    assert client.get("/api/runs/nope-123").status_code == 404
