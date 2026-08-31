"""M0 smoke: the suite scaffold imports, fixtures wire, seams work."""
from __future__ import annotations


def test_health(client_mock):
    r = client_mock.get("/health")
    assert r.status_code == 200
    # Checked by key, not whole-body equality: /health also reports
    # `render_concurrency` (how many slides this server draws at once,
    # which the client cannot guess and sizes its queue by), and an
    # exact-match assertion makes every future field a failure here.
    body = r.json()
    assert body["status"] == "ok"
    assert body["render_concurrency"] >= 1


def test_synthetic_model_loads(synthetic_model):
    df, model = synthetic_model
    assert len(df) == 5
    assert any(q.qid == "q1" for q in model.questions)


def test_memory_client_roundtrips_a_case(client_memory):
    cust = client_memory.post("/customers", json={"name": "smoke"}).json()["id"]
    r = client_memory.post(f"/customers/{cust}/cases", json={"name": "smoke"})
    assert r.status_code in (200, 201)
    assert r.json()["id"]


def test_recording_chat(canned_chat):
    chat = canned_chat("hello")
    assert chat("some prompt") == "hello"
    assert chat.calls == 1
    assert chat.prompts == ["some prompt"]
