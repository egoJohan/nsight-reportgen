"""M0 smoke: the suite scaffold imports, fixtures wire, seams work."""
from __future__ import annotations


def test_health(client_mock):
    r = client_mock.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_synthetic_model_loads(synthetic_model):
    df, model = synthetic_model
    assert len(df) == 5
    assert any(q.qid == "q1" for q in model.questions)


def test_memory_client_roundtrips_a_case(client_memory):
    r = client_memory.post("/cases", json={"name": "smoke"})
    assert r.status_code in (200, 201)
    assert r.json()["case_id"]


def test_recording_chat(canned_chat):
    chat = canned_chat("hello")
    assert chat("some prompt") == "hello"
    assert chat.calls == 1
    assert chat.prompts == ["some prompt"]
