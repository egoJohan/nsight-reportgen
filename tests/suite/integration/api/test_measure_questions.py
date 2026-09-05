"""A continuous measure, as the question browser sees it.

It is a question — its mean is a finding — but it is not one of the study's
asked questions, and a file can carry dozens of them (this customer's carries
thirteen rescaled recodes beside its six indices). So the browser is told which
ones they are: it can keep them out of the default list, offer them behind
"show them", and start such a slide on the statistic that suits it.
"""
from __future__ import annotations

import pandas as pd
import pyreadstat
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def measures_bytes(tmp_path):
    path = tmp_path / "measures.sav"
    df = pd.DataFrame({
        "tyoelamaindeksi": [50.0 + (i % 400) * 0.13 for i in range(200)],
        "q1": [float(i % 2 + 1) for i in range(200)],
        "sukupuoli": [float(i % 2 + 1) for i in range(200)],
    })
    pyreadstat.write_sav(
        df, str(path),
        column_labels={"tyoelamaindeksi": None, "q1": "Suositteletko?",
                       "sukupuoli": "Sukupuoli"},
        variable_value_labels={"q1": {1: "Kyllä", 2: "Ei"},
                               "sukupuoli": {1: "Nainen", 2: "Mies"}},
        variable_measure={"tyoelamaindeksi": "scale", "q1": "nominal",
                          "sukupuoli": "nominal"},
    )
    return path.read_bytes()


@pytest.fixture
def material(client_memory, measures_bytes):
    c = client_memory
    cid = c.post("/customers", json={"name": "A"}).json()["id"]
    kid = c.post(f"/customers/{cid}/cases", json={"name": "T"}).json()["id"]
    mid = c.post(f"/cases/{kid}/materials",
                 files={"file": ("m.sav", measures_bytes,
                                 "application/octet-stream")}).json()["material_id"]
    return c, mid


def _q(client, mid, needle):
    qs = client.get(f"/materials/{mid}/questions").json()["questions"]
    return next(q for q in qs if needle in q["qid"] or needle in (q["text"] or ""))


def test_the_measure_is_offered_as_a_question(material):
    client, mid = material
    assert _q(client, mid, "tyoelamaindeksi")["chartable"] is True


def test_it_is_marked_as_a_measure_so_the_browser_can_hold_it_back(material):
    client, mid = material
    q = _q(client, mid, "tyoelamaindeksi")
    assert q["is_measure"] is True
    assert q["offered_by_default"] is False
    assert q["held_back_because"]


def test_an_asked_question_is_neither(material):
    client, mid = material
    q = _q(client, mid, "Suositteletko?")
    assert q["is_measure"] is False
    assert q["offered_by_default"] is True


def test_a_measure_starts_on_the_statistic_that_suits_it(material):
    """A distribution of 400 distinct values is an empty slide; its mean is the
    finding, so that is where such a slide starts."""
    client, mid = material
    assert _q(client, mid, "tyoelamaindeksi")["suggested_statistic"] == "mean"
    assert _q(client, mid, "Suositteletko?")["suggested_statistic"] == "pct"
