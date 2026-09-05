"""The label editor offers the categories the chart actually draws.

Reported: "Mulla on vaikeuksia määrittää legendissä muuttujien arvojen
labeleita. Kuinka saan valitun lyhyen tekstin mukaan arvon labeliksi ettei
tarvitsisi viedä selitystekstejä subtitleen" — with a legend reading 1..7 and
the meaning pushed into the subtitle.

A 1..7 scale labelled only at its ENDPOINTS is charted as seven numbered
categories, with the endpoint wording moved to a caption. The editor, though,
listed the variable's value labels — the two endpoints — so the five middle
points could not be named at all, and a short text typed against "Täysin eri
mieltä" was stored under a name no category has, which is why the edit did not
render.
"""
from __future__ import annotations

import pandas as pd
import pyreadstat
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def endpoints_sav(tmp_path):
    path = tmp_path / "endpoints.sav"
    df = pd.DataFrame({
        "q1": [float(i % 7 + 1) for i in range(700)],
        "maa": [float(i % 3 + 1) for i in range(700)],
    })
    pyreadstat.write_sav(
        df, str(path),
        column_labels={"q1": "Koen, että omalla alallani on hyvät mahdollisuudet",
                       "maa": "Maa"},
        # Only the endpoints carry text — the shape this is about.
        variable_value_labels={"q1": {1: "Täysin eri mieltä", 7: "Täysin samaa mieltä"},
                               "maa": {1: "Suomi", 2: "Ruotsi", 3: "Saksa"}},
        variable_measure={"q1": "nominal", "maa": "nominal"},
    )
    return path.read_bytes()


@pytest.fixture
def material(client_memory, endpoints_sav):
    c = client_memory
    cid = c.post("/customers", json={"name": "A"}).json()["id"]
    kid = c.post(f"/customers/{cid}/cases", json={"name": "T"}).json()["id"]
    mid = c.post(f"/cases/{kid}/materials",
                 files={"file": ("e.sav", endpoints_sav,
                                 "application/octet-stream")}).json()["material_id"]
    return c, mid


def _q1(client, mid):
    qs = client.get(f"/materials/{mid}/questions").json()["questions"]
    return next(q for q in qs if q["qid"] == "q1")


def test_the_editor_lists_all_seven_points(material):
    client, mid = material
    assert set(_q1(client, mid)["category_labels"]) == {"1", "2", "3", "4", "5", "6", "7"}


def test_it_lists_them_in_the_order_they_are_drawn(material):
    client, mid = material
    assert _q1(client, mid)["category_labels"] == ["7", "6", "5", "4", "3", "2", "1"]


def test_a_fully_labelled_scale_still_lists_its_words(client_memory, tmp_path):
    """Unchanged where every point carries text — those ARE the categories."""
    path = tmp_path / "full.sav"
    df = pd.DataFrame({"q1": [float(i % 3 + 1) for i in range(90)]})
    pyreadstat.write_sav(
        df, str(path), column_labels={"q1": "Kuinka tyytyväinen?"},
        variable_value_labels={"q1": {1: "Huono", 2: "Keskinkertainen", 3: "Hyvä"}},
        variable_measure={"q1": "nominal"})
    c = client_memory
    cid = c.post("/customers", json={"name": "B"}).json()["id"]
    kid = c.post(f"/customers/{cid}/cases", json={"name": "T"}).json()["id"]
    mid = c.post(f"/cases/{kid}/materials",
                 files={"file": ("f.sav", path.read_bytes(),
                                 "application/octet-stream")}).json()["material_id"]
    qs = c.get(f"/materials/{mid}/questions").json()["questions"]
    q = next(x for x in qs if x["qid"] == "q1")
    assert set(q["category_labels"]) == {"Huono", "Keskinkertainen", "Hyvä"}


def test_a_short_text_typed_against_a_point_reaches_the_legend(
        material, endpoints_sav, tmp_path):
    """The whole point of the report: name the values instead of explaining them
    in the subtitle. The editor's rows and the chart's categories are the same
    strings now, so an override matches what is drawn."""
    from reportbuilder.ingest.sav_reader import read_sav
    from reportbuilder.model.report import (
        ChartSpec, ElementToggles, NumberFormat, SortSpec,
    )
    from reportbuilder.stats.engine import compute

    client, mid = material
    listed = _q1(client, mid)["category_labels"]
    # exactly what an author would do in the editor: rename the two ends
    overrides = (("7", "Täysin samaa mieltä"), ("1", "Täysin eri mieltä"))
    assert all(orig in listed for orig, _short in overrides)

    path = tmp_path / "again.sav"
    path.write_bytes(endpoints_sav)
    df, model = read_sav(str(path))
    spec = ChartSpec(
        question_ref="q1", chart_type="stacked_horizontal_bar", statistic="pct",
        classifying_var="maa", number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s",
        elements=ElementToggles(), category_label_overrides=overrides)
    r = compute(model.question("q1"), spec, df, model)
    assert "Täysin samaa mieltä" in r.categories
    assert "Täysin eri mieltä" in r.categories
    assert "7" not in r.categories and "1" not in r.categories
