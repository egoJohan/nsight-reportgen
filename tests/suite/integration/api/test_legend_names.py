"""The names a slide's legend shows that are not the question's answers.

The labels editor lists them under the answers so an author can rename them.
Asked of the server, from the chart as it is computed, so the list is exactly
what the slide draws — not the editor's guess about which chart types have a
legend of groups. (Johan, 2026-09-17)
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


def _pick(client, mid):
    qs = client.get(f"/materials/{mid}/questions").json()["questions"]
    variables = client.get(f"/materials/{mid}/variables").json()["variables"]
    clf = [v["name"] for v in variables if v.get("segmentable")]
    q = next(q for q in qs if q.get("kind") == "single" and q.get("chartable", True)
             and q["variables"][0] not in clf[:1])
    # A cross-tab needs a SECOND classifier; any other small labelled variable.
    clf += [v["name"] for v in variables
            if v["name"] not in clf and v["name"] != q["variables"][0]
            and v.get("measurement") == "categorical" and 2 <= (v.get("n_values") or 0) <= 6]
    return q, clf


def _body(q, **kw):
    return {"question_ref": q["qid"], "chart_type": "vertical_bar", **kw}


def test_a_split_slide_names_its_groups(case_with_data):
    client, mid = case_with_data
    q, clf = _pick(client, mid)
    groups = client.get(f"/materials/{mid}/questions/{q['qid']}/segments",
                        params={"classifying_var": clf[0]}).json()["segments"]
    r = client.post(f"/materials/{mid}/legend-names",
                    json=_body(q, classifying_var=clf[0]))
    assert r.status_code == 200, r.text
    assert r.json()["names"] == groups
    assert "Total" not in r.json()["names"]


def test_a_slide_with_no_split_has_nothing_to_name(case_with_data):
    client, mid = case_with_data
    q, _clf = _pick(client, mid)
    r = client.post(f"/materials/{mid}/legend-names", json=_body(q))
    assert r.status_code == 200
    assert r.json()["names"] == []


def test_names_are_the_datas_own_not_the_renamed_ones(case_with_data):
    """The editor keys a rename on the original name, so it must be offered
    that — and still find it after the author has renamed it."""
    client, mid = case_with_data
    q, clf = _pick(client, mid)
    plain = client.post(f"/materials/{mid}/legend-names",
                        json=_body(q, classifying_var=clf[0])).json()["names"]
    renamed = client.post(f"/materials/{mid}/legend-names", json=_body(
        q, classifying_var=clf[0],
        series_label_overrides=[[plain[0], "Uusi nimi"]],
        category_label_overrides=[[plain[0], "Toinen"]])).json()["names"]
    assert renamed == plain


def test_a_cross_tab_offers_the_parts_of_its_combinations(monkeypatch):
    """The synthetic file has one classifier, so the cross-tab branch is driven
    with a computed series that IS a cross-tab (`segment_primary` set). Each
    part is a name drawn on its own, so the parts are what is offered."""
    from reportbuilder.api import routes_questions as rq
    from reportbuilder.stats.series import Cell, SeriesResult

    crossed = SeriesResult(
        categories=("A",), segments=("Mies · Nuori", "Nainen · Nuori"),
        cells={("A", s): Cell(pct=50.0) for s in ("Mies · Nuori", "Nainen · Nuori")},
        base_n={"Total": 2}, statistic="pct",
        segment_primary={"Mies · Nuori": "Mies", "Nainen · Nuori": "Nainen"})

    class _Model:
        def question(self, qid):
            return object()

    monkeypatch.setattr(rq, "df_model_for_material", lambda *a, **k: (None, _Model()))
    monkeypatch.setattr(rq, "compute", lambda *a, **k: crossed)
    body = rq.ChartSpecBody(question_ref="q", chart_type="vertical_bar",
                            classifying_var="a", classifying_var_2="b")
    assert rq.legend_names("m", body, client=None, user=None) == {
        "names": ["Mies", "Nuori", "Nainen"], "cross_tab": True}


def test_an_unknown_question_is_404(case_with_data):
    client, mid = case_with_data
    r = client.post(f"/materials/{mid}/legend-names",
                    json={"question_ref": "nope", "chart_type": "vertical_bar"})
    assert r.status_code == 404
