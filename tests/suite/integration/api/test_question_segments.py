"""The groups a question splits into — what a scatter plots against each other.

A scatter positions each CATEGORY by its value in two segments (wave 1 against
wave 2, our brand against a competitor), so configuring one means naming two
groups, and only the data knows what they are called. This is where the picker
gets them.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def case_with_data(client_memory, synthetic_bytes):
    cid = client_memory.post("/customers", json={"name": "Asiakas"}).json()["id"]
    kid = client_memory.post(f"/customers/{cid}/cases",
                             json={"name": "Tutkimus"}).json()["id"]
    mid = client_memory.post(
        f"/cases/{kid}/materials",
        files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
    ).json()["material_id"]
    return client_memory, mid


def _first(client, mid):
    qs = client.get(f"/materials/{mid}/questions").json()["questions"]
    variables = client.get(f"/materials/{mid}/variables").json()["variables"]
    clf = next((v["name"] for v in variables if v.get("segmentable")), None)
    qid = next((q["qid"] for q in qs if q.get("chartable", True)), None)
    return qid, clf


def test_it_lists_the_groups(case_with_data):
    client, mid = case_with_data
    qid, clf = _first(client, mid)
    r = client.get(f"/materials/{mid}/questions/{qid}/segments",
                   params={"classifying_var": clf})
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["segments"], list)


def test_total_is_not_offered(case_with_data):
    """Every respondent is not a group. Plotting it against one of its own
    parts compares a thing with itself."""
    client, mid = case_with_data
    qid, clf = _first(client, mid)
    segs = client.get(f"/materials/{mid}/questions/{qid}/segments",
                      params={"classifying_var": clf}).json()["segments"]
    assert "Total" not in segs


def test_an_unknown_question_is_404(case_with_data):
    client, mid = case_with_data
    _qid, clf = _first(client, mid)
    assert client.get(f"/materials/{mid}/questions/nope/segments",
                      params={"classifying_var": clf}).status_code == 404


def test_a_nonsense_classifier_yields_nothing_rather_than_500(case_with_data):
    """A picker that cannot be filled must not stop somebody configuring the
    rest of the slide."""
    client, mid = case_with_data
    qid, _clf = _first(client, mid)
    r = client.get(f"/materials/{mid}/questions/{qid}/segments",
                   params={"classifying_var": "no_such_variable"})
    assert r.status_code == 200 and r.json()["segments"] == []
