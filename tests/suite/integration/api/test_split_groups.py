"""Which questions does a classifier actually split?

The "Compare groups" dialog must not offer a question whose split yields one
group — 6 of the customer's 18 do, every one a battery whose members belong to a
single study arm. (spec 2026-08-02-compare-groups-section §1.1)
"""
from __future__ import annotations

import json
import pathlib

import pytest

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

# The .sav and the saved report are read from the OLD store's directory, which
# still exists on disk after the legacy code was removed — the data was left
# unread, not deleted. They are fixture INPUT here: the material is uploaded
# into a fresh in-memory store, so the test exercises the current storage path
# rather than the retired one.
_FIXTURES = pathlib.Path("work/demo-store")


@pytest.fixture
def client_and_material():
    _require_fixture()
    store = InMemoryObjectStore()
    repo = Repository(store)
    auth = AuthContext(token="test")

    customer = repo.create_customer(auth, "Erisan")
    case = repo.create_case(auth, customer.id, "Erisan-tutkimus")
    material = repo.attach_material(
        auth, customer.id, case.id, "erisan.sav",
        (_FIXTURES / "materials" / "mat-erisan.sav").read_bytes())

    from fastapi.testclient import TestClient
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    return TestClient(app), material.id


def _require_fixture():
    if not (_FIXTURES / "materials" / "mat-erisan.sav").exists():
        pytest.skip("mat-erisan fixture not available locally")


def _grouping() -> str:
    rep = json.loads(json.loads((_FIXTURES / "reports.json").read_text())["rep-erisan"])
    return json.dumps(rep["grouping"])


def test_reports_two_groups_for_a_question_everyone_answered(client_and_material):
    client, material_id = client_and_material
    r = client.get(f"/materials/{material_id}/split-groups",
                   params={"classifying_var": "polku"})
    assert r.status_code == 200
    assert r.json()["groups"]["var3"] == 2


def test_reports_one_group_for_a_single_arm_battery(client_and_material):
    """A battery asked only of path 1 yields that arm and nothing else."""
    client, material_id = client_and_material
    r = client.get(f"/materials/{material_id}/split-groups",
                   params={"classifying_var": "polku", "grouping": _grouping()})
    groups = r.json()["groups"]
    single_arm = [q for q, n in groups.items() if q.startswith("battery-") and n < 2]
    assert len(single_arm) >= 6, groups


def test_the_string_encoding_agrees_with_the_banner_one(client_and_material):
    """var214 and polku describe the same split, so they must disable the same
    questions — otherwise the dialog contradicts the chart."""
    client, material_id = client_and_material
    a = client.get(f"/materials/{material_id}/split-groups",
                   params={"classifying_var": "polku", "grouping": _grouping()}).json()["groups"]
    b = client.get(f"/materials/{material_id}/split-groups",
                   params={"classifying_var": "var214", "grouping": _grouping()}).json()["groups"]
    assert {q for q, n in a.items() if n >= 2} == {q for q, n in b.items() if n >= 2}


def test_unknown_classifier_reports_no_groups(client_and_material):
    client, material_id = client_and_material
    r = client.get(f"/materials/{material_id}/split-groups",
                   params={"classifying_var": "does-not-exist"})
    assert r.status_code == 200
    assert all(n < 2 for n in r.json()["groups"].values())


def test_missing_classifier_is_a_422(client_and_material):
    client, material_id = client_and_material
    assert client.get(f"/materials/{material_id}/split-groups").status_code == 422
