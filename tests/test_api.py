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
