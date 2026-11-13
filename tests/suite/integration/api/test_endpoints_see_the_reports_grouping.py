"""The editor's endpoints see the questions the report's grouping makes.

A report's grouping is applied to the FILE's own model: the author's groups
first, the automatic suggestions only to what is left. The endpoints that take
a `grouping` parameter used to apply it on top of a model that had already been
grouped automatically, so a variable the automatic pass had put into a battery
was spoken for, the author's group never formed, and its question 404'd.

Synsam, staging 2026-11-13: tick-boxes `Laadukas_SYNSAM`, `Kallis_SYNSAM`, …
(label "Synsam:Laadukas:<question>"), four brands by four adjectives, grouped by the author as one brand's
multi-response question `laadukas_synsam`. Automatically they form one battery
per adjective across brands. `/segments` answered 404, so the "Groups on this
slide" picker vanished and 2025/2026 could not be chosen; the slide itself
rendered, because rendering applies the grouping in the right order.
"""
from __future__ import annotations

import json

import pandas as pd
import pyreadstat
import pytest

pytestmark = pytest.mark.integration

_Q = "Mitä seuraavista ominaisuuksista liität seuraaviin tuotemerkkeihin?"
_BRANDS = ("SYNSAM", "INSTRUMENTARIUM", "SPECSAVERS", "SILMÄASEMA")
_ADJS = ("Laadukas", "Kallis", "Luotettava", "Suosittu")


def _sav(path) -> bytes:
    n = 40
    data = {"Ajankohta": [1.0 if i % 2 else 2.0 for i in range(n)]}
    labels = {"Ajankohta": "Kyselyn ajankohta"}
    vlabels = {"Ajankohta": {1.0: "2026", 2.0: "2025"}}
    for a_i, adj in enumerate(_ADJS):
        for b_i, brand in enumerate(_BRANDS):
            v = f"{adj}_{brand}"
            data[v] = [float((i + a_i + b_i) % 3 == 0) for i in range(n)]
            labels[v] = f"{brand.title()}:{adj}:{_Q}"
            vlabels[v] = {0.0: "Unchecked", 1.0: "Checked"}
    df = pd.DataFrame(data)
    pyreadstat.write_sav(df, str(path), column_labels=[labels[c] for c in df.columns],
                         variable_value_labels=vlabels)
    return path.read_bytes()


@pytest.fixture
def grouped(client_memory, tmp_path):
    client = client_memory
    cid = client.post("/customers", json={"name": "Asiakas"}).json()["id"]
    kid = client.post(f"/customers/{cid}/cases", json={"name": "Tutkimus"}).json()["id"]
    mid = client.post(
        f"/cases/{kid}/materials",
        files={"file": ("s.sav", _sav(tmp_path / "s.sav"), "application/octet-stream")},
    ).json()["material_id"]
    grouping = {"groups": [{"kind": "multi", "label": "",
                            "variables": [f"{a}_SYNSAM" for a in _ADJS]}],
                "singles": []}
    # The qid the report stores is the one the grouping endpoint hands out.
    qs = client.post(f"/materials/{mid}/regroup", json=grouping)
    assert qs.status_code == 200, qs.text
    qid = next(q["qid"] for q in qs.json()["questions"]
               if q.get("kind") == "multi" and "Laadukas_SYNSAM" in q.get("variables", []))
    return client, mid, qid, json.dumps(grouping)


def test_the_group_picker_finds_the_authors_group(grouped):
    client, mid, qid, grouping = grouped
    r = client.get(f"/materials/{mid}/questions/{qid}/segments",
                   params={"classifying_var": "Ajankohta", "grouping": grouping})
    assert r.status_code == 200, r.text
    assert r.json()["segments"] == ["2026", "2025"]


def test_the_panel_warning_finds_it(grouped):
    client, mid, qid, grouping = grouped
    r = client.get(f"/materials/{mid}/questions/{qid}/panels",
                   params={"classifying_var": "Ajankohta", "grouping": grouping})
    assert r.status_code == 200, r.text


def test_the_question_details_find_it(grouped):
    client, mid, qid, grouping = grouped
    r = client.get(f"/materials/{mid}/questions/{qid}/summary", params={"grouping": grouping})
    assert r.status_code == 200, r.text
