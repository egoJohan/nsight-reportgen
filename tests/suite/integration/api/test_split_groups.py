"""Which questions does a classifier actually split?

The "Compare groups" dialog must not offer a question whose split yields one
group — 6 of the customer's 18 do, every one a battery whose members belong to a
single study arm. (spec 2026-08-02-compare-groups-section §1.1)
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest

_STORE = pathlib.Path("work/demo-store")


@pytest.fixture
def client():
    os.environ["NSIGHT_DEMO"] = "1"
    os.environ["NSIGHT_DEMO_DIR"] = str(_STORE)
    from fastapi.testclient import TestClient

    from reportbuilder.api.server import build_server_app

    return TestClient(build_server_app())


def _require_fixture():
    if not (_STORE / "materials" / "mat-erisan.sav").exists():
        pytest.skip("mat-erisan not available locally")


def _grouping() -> str:
    rep = json.loads(json.loads((_STORE / "reports.json").read_text())["rep-erisan"])
    return json.dumps(rep["grouping"])


def test_reports_two_groups_for_a_question_everyone_answered(client):
    _require_fixture()
    r = client.get("/materials/mat-erisan/split-groups",
                   params={"classifying_var": "polku"})
    assert r.status_code == 200
    assert r.json()["groups"]["var3"] == 2


def test_reports_one_group_for_a_single_arm_battery(client):
    """A battery asked only of path 1 yields that arm and nothing else."""
    _require_fixture()
    r = client.get("/materials/mat-erisan/split-groups",
                   params={"classifying_var": "polku", "grouping": _grouping()})
    groups = r.json()["groups"]
    single_arm = [q for q, n in groups.items() if q.startswith("battery-") and n < 2]
    assert len(single_arm) >= 6, groups


def test_the_string_encoding_agrees_with_the_banner_one(client):
    """var214 and polku describe the same split, so they must disable the same
    questions — otherwise the dialog contradicts the chart."""
    _require_fixture()
    a = client.get("/materials/mat-erisan/split-groups",
                   params={"classifying_var": "polku", "grouping": _grouping()}).json()["groups"]
    b = client.get("/materials/mat-erisan/split-groups",
                   params={"classifying_var": "var214", "grouping": _grouping()}).json()["groups"]
    assert {q for q, n in a.items() if n >= 2} == {q for q, n in b.items() if n >= 2}


def test_unknown_classifier_reports_no_groups(client):
    _require_fixture()
    r = client.get("/materials/mat-erisan/split-groups",
                   params={"classifying_var": "does-not-exist"})
    assert r.status_code == 200
    assert all(n < 2 for n in r.json()["groups"].values())


def test_missing_classifier_is_a_422(client):
    _require_fixture()
    assert client.get("/materials/mat-erisan/split-groups").status_code == 422
