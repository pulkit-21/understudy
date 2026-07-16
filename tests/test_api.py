"""API contract tests (through the real HTTP layer, no browser).

Covers the trace -> induce -> workflow path and the recording endpoints'
guardrails. The headful recording itself needs a display and is exercised
locally, not in CI; here we pin the error contracts and the induction result.
"""
from fastapi.testclient import TestClient

from app.main import app, traces
from tests.conftest import demo_trace as _demo_trace_fixture

client = TestClient(app)


def _seed_trace():
    trace = _demo_trace_fixture.__wrapped__()
    traces.save(trace)
    return trace


def test_stop_unknown_recording_is_404():
    assert client.post("/api/recordings/does-not-exist/stop").status_code == 404


def test_list_recordings_returns_a_list():
    r = client.get("/api/recordings")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_induce_via_api_yields_invoice_id_only_spec():
    trace = _seed_trace()
    r = client.post(f"/api/traces/{trace.id}/induce", json={"use_llm": False})
    assert r.status_code == 200
    body = r.json()
    assert body["problems"] == []
    spec = body["workflow"]
    assert [p["key"] for p in spec["parameters"]] == ["invoice_id"]
    assert body["induced_by"] == "heuristic"


def test_put_workflow_rejects_an_ungated_commit_step():
    """The API must refuse to save a spec whose commit step lost its gate —
    the safety invariant is enforced at the edit boundary, not just in code."""
    trace = _seed_trace()
    induced = client.post(f"/api/traces/{trace.id}/induce",
                          json={"use_llm": False}).json()["workflow"]
    wf_id = induced["id"]
    for step in induced["steps"]:
        if step["risk"] == "commit":
            step["requires_approval"] = False
    r = client.put(f"/api/workflows/{wf_id}", json=induced)
    assert r.status_code == 422
