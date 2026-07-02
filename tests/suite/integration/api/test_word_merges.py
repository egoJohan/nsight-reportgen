"""Word-cloud value merges — per-question, material-level (case-page dialog).

PUT saves {label, words} groups into the material config; GET returns the question's
raw top words (for the editor) plus the current merges. The merge folds variant token
counts into one word in the word cloud (engine-level test covers the summing).
"""
from __future__ import annotations


def _case_material(client, synthetic_bytes) -> str:
    cid = client.post("/cases", json={"name": "A"}).json()["case_id"]
    return client.post(
        f"/cases/{cid}/materials",
        files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
    ).json()["material_id"]


def test_put_and_get_word_merges_roundtrip(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    r = client_memory.put(
        f"/materials/{mid}/questions/q1/word-merges",
        json={"merges": [{"label": "Esperi", "words": ["Esperi", "esper"]}]},
    )
    assert r.status_code == 200
    got = client_memory.get(f"/materials/{mid}/questions/q1/words").json()
    # words are lowercased for matching; label keeps its display case.
    assert got["merges"] == [{"label": "Esperi", "words": ["esperi", "esper"]}]


def test_empty_merges_clears(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    client_memory.put(
        f"/materials/{mid}/questions/q1/word-merges",
        json={"merges": [{"label": "Esperi", "words": ["esperi", "esper"]}]},
    )
    client_memory.put(f"/materials/{mid}/questions/q1/word-merges", json={"merges": []})
    assert client_memory.get(f"/materials/{mid}/questions/q1/words").json()["merges"] == []


def test_word_merges_preserve_question_label(client_memory, synthetic_bytes):
    """Saving merges must not clobber a stored question rename (same config blob)."""
    mid = _case_material(client_memory, synthetic_bytes)
    client_memory.patch(f"/materials/{mid}/questions/q1/label", json={"label": "Renamed"})
    client_memory.put(
        f"/materials/{mid}/questions/q1/word-merges",
        json={"merges": [{"label": "X", "words": ["a", "b"]}]},
    )
    qs = client_memory.get(f"/materials/{mid}/questions").json()["questions"]
    assert next(q["text"] for q in qs if q["qid"] == "q1") == "Renamed"


def test_get_words_returns_list_shape(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    body = client_memory.get(f"/materials/{mid}/questions/q1/words").json()
    assert "words" in body and "merges" in body
    assert isinstance(body["words"], list)
