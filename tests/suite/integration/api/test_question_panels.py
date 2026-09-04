"""What a one-panel-per-group chart would actually draw.

The editor's warning used to say "the three largest will be drawn and the rest
left out" while knowing only how many values the variable HAS. It could not name
them, and its arithmetic was wrong whenever a group fell under the reporting
base — those are dropped first, for a different reason, and reported under a
different heading on the slide.

So the editor asks the same function the renderer uses. These tests exist to
keep the two from drifting apart, which `render/panels.py` says in its own
docstring is the whole point of that module.
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


def _first_classifiable(client, mid):
    qs = client.get(f"/materials/{mid}/questions").json()["questions"]
    variables = client.get(f"/materials/{mid}/variables").json()["variables"]
    clf = next((v["name"] for v in variables if v.get("segmentable")), None)
    qid = next((q["qid"] for q in qs if q.get("chartable", True)), None)
    return qid, clf


def test_it_names_what_would_be_drawn(case_with_data):
    client, mid = case_with_data
    qid, clf = _first_classifiable(client, mid)
    assert qid and clf, "fixture should offer a chartable question and a classifier"
    r = client.get(f"/materials/{mid}/questions/{qid}/panels",
                   params={"classifying_var": clf})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"drawn", "thin", "capped", "degraded", "split",
                         "max_panels"}
    assert isinstance(body["drawn"], list)


def test_it_never_draws_more_than_the_cap(case_with_data):
    client, mid = case_with_data
    qid, clf = _first_classifiable(client, mid)
    body = client.get(f"/materials/{mid}/questions/{qid}/panels",
                      params={"classifying_var": clf}).json()
    if body["max_panels"]:
        assert len(body["drawn"]) <= body["max_panels"]


def test_the_two_reasons_are_kept_apart(case_with_data):
    """A thin group could not be reported; a capped one did not fit. The slide
    footer prints them under different headings, so the warning must not merge
    them into one count."""
    client, mid = case_with_data
    qid, clf = _first_classifiable(client, mid)
    body = client.get(f"/materials/{mid}/questions/{qid}/panels",
                      params={"classifying_var": clf}).json()
    assert set(body["thin"]) & set(body["capped"]) == set()
    assert set(body["drawn"]) & set(body["capped"]) == set()


def test_an_unknown_question_is_404(case_with_data):
    client, mid = case_with_data
    _qid, clf = _first_classifiable(client, mid)
    r = client.get(f"/materials/{mid}/questions/nope/panels",
                   params={"classifying_var": clf})
    assert r.status_code == 404


def test_a_nonsense_classifier_does_not_500(case_with_data):
    """A warning that cannot be computed must not stop somebody configuring a
    slide."""
    client, mid = case_with_data
    qid, _clf = _first_classifiable(client, mid)
    r = client.get(f"/materials/{mid}/questions/{qid}/panels",
                   params={"classifying_var": "no_such_variable"})
    assert r.status_code == 200, r.text
    # Not split into panels, so there is nothing to warn about — as opposed to
    # "split, and everything was dropped", which would be alarming and false.
    assert r.json()["split"] is False
    assert r.json()["capped"] == []


# ── the warning must describe THIS slide ─────────────────────────────────────

@pytest.fixture
def five_group_case(client_memory, tmp_path):
    """A classifier with five well-populated groups — the shared fixture has
    five ROWS, so every group there is under the reporting base and no chart
    ever splits into panels."""
    import pandas as pd
    import pyreadstat

    rows = 250
    df = pd.DataFrame({
        "q1": [1.0 if i % 5 else 2.0 for i in range(rows)],
        "g": [float(i % 5 + 1) for i in range(rows)],
    })
    path = tmp_path / "five.sav"
    pyreadstat.write_sav(
        df, str(path),
        column_labels={"q1": "Suositteletko?", "g": "Ryhmä"},
        variable_value_labels={
            "q1": {1: "Kyllä", 2: "Ei"},
            "g": {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"},
        },
        variable_measure={"q1": "nominal", "g": "nominal"},
    )
    c = client_memory
    cid = c.post("/customers", json={"name": "Asiakas"}).json()["id"]
    kid = c.post(f"/customers/{cid}/cases", json={"name": "Tutkimus"}).json()["id"]
    mid = c.post(f"/cases/{kid}/materials",
                 files={"file": ("five.sav", path.read_bytes(),
                                 "application/octet-stream")}).json()["material_id"]
    qid = next(q["qid"] for q in c.get(f"/materials/{mid}/questions").json()["questions"]
               if q["qid"] == "q1")
    return c, mid, qid


def test_five_groups_are_capped_to_three(five_group_case):
    client, mid, qid = five_group_case
    body = client.get(f"/materials/{mid}/questions/{qid}/panels",
                      params={"classifying_var": "g"}).json()
    assert body["split"] is True, body
    assert len(body["drawn"]) == 3, body
    assert len(body["capped"]) == 2, body


def test_the_warning_answers_for_the_GROUPS_THE_SLIDE_DRAWS(five_group_case):
    """Reported: a five-group classifier warns that only three panels fit, which
    is true; the author then picks three, and the warning stays — naming a
    selection of its own, not theirs. The warning was computed on the whole
    variable while the slide was computed on part of it, so the two disagreed
    about what the slide contains, which `render/panels.py` exists to prevent.
    """
    client, mid, qid = five_group_case
    body = client.get(f"/materials/{mid}/questions/{qid}/panels",
                      params={"classifying_var": "g",
                              "classifying_values": ["A", "C", "E"]}).json()
    assert body["drawn"] == ["A", "C", "E"], body
    assert body["capped"] == [], body
    assert body["thin"] == [], body


