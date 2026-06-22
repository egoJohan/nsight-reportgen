from fastapi.testclient import TestClient
from nsight.webapp.app import create_app


def test_list_inputs_endpoint():
    app = create_app()
    client = TestClient(app)
    r = client.get("/api/inputs")
    assert r.status_code == 200
    body = r.json()
    assert "savs" in body and "briefs" in body


def test_run_returns_report(monkeypatch):
    import nsight.webapp.app as appmod

    def fake_run(sav, brief):
        return {"chart_score": 95.0, "mismatches": [], "deck_path": "/tmp/x.pptx"}

    monkeypatch.setattr(appmod, "run_generation", fake_run)
    client = TestClient(create_app())
    r = client.post("/api/run", json={"sav": "a.sav", "brief": "attendo.md"})
    assert r.status_code == 200
    assert r.json()["chart_score"] == 95.0
