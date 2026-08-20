"""Listings must not leak another customer's existence.

Spec §5.3: these seven calls used to be filtered by datahive, because nSight
talked to it as the logged-in user. Holding a tenant-wide service token instead
means each one returns the whole tenant unless it filters here. Nothing throws
when this regresses — hence these tests.
"""
import json

import pytest

from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def tree(repo, auth):
    """Two customers, one case each, one report each, one material each."""
    a = repo.create_customer(auth, "Attendo")
    b = repo.create_customer(auth, "Synsam")
    ka = repo.create_case(auth, a.id, "A-study")
    kb = repo.create_case(auth, b.id, "B-study")
    repo.save_report(auth, a.id, ka.id, json.dumps({"name": "A-report"}))
    repo.save_report(auth, b.id, kb.id, json.dumps({"name": "B-report"}))
    ma = repo.attach_material(auth, a.id, ka.id, "a.sav", b"SAV")
    mb = repo.attach_material(auth, b.id, kb.id, "b.sav", b"SAV")
    return {"a": a, "b": b, "ka": ka, "kb": kb, "ma": ma, "mb": mb}


@pytest.fixture
def only_a(tree):
    return User(id="u", email="a@b.c", grants=(Grant(tree["a"].id, "edit"),))


def test_list_customers_hides_the_other_customer(repo, auth, tree, only_a):
    assert [c.name for c in repo.list_customers(auth, user=only_a)] == ["Attendo"]


def test_list_cases_refuses_an_ungranted_customer(repo, auth, tree, only_a):
    assert repo.list_cases(auth, tree["b"].id, user=only_a) == []


def test_find_case_does_not_resolve_an_ungranted_case(repo, auth, tree, only_a):
    assert repo.find_case(auth, tree["kb"].id, user=only_a) is None
    assert repo.find_case(auth, tree["ka"].id, user=only_a) is not None


def test_find_material_does_not_resolve_an_ungranted_material(repo, auth, tree, only_a):
    """The seventeen material-addressed routes rest on this (spec §5.1): a
    material id is not authorisation."""
    assert repo.find_material(auth, tree["mb"].id, user=only_a) is None
    assert repo.find_material(auth, tree["ma"].id, user=only_a) is not None


def test_list_materials_refuses_an_ungranted_case(repo, auth, tree, only_a):
    assert repo.list_materials(auth, tree["b"].id, tree["kb"].id, user=only_a) == []


def test_list_reports_refuses_an_ungranted_case(repo, auth, tree, only_a):
    assert repo.list_reports(auth, tree["b"].id, tree["kb"].id, user=only_a) == []


def test_recent_reports_spans_only_granted_customers(repo, auth, tree, only_a):
    """The landing page. Unfiltered, it shows everyone's work to everyone."""
    names = [r.name for r in repo.recent_reports(auth, user=only_a)]
    assert names == ["A-report"]


def test_a_case_grant_sees_its_case_but_not_its_customer(repo, auth, tree):
    u = User(id="u", email="a@b.c",
             grants=(Grant(f"{tree['a'].id}/{tree['ka'].id}", "view"),))
    assert [c.name for c in repo.list_customers(auth, user=u)] == []
    assert repo.find_case(auth, tree["ka"].id, user=u) is not None


def test_a_grant_to_a_deleted_customer_is_inert(repo, auth, tree):
    """Spec §5: "a grant naming a customer or case that no longer exists is
    ignored", the way a template binding to a deleted file is. It must not
    match by accident and it must not raise."""
    u = User(id="u", email="a@b.c", grants=(Grant("cust-gone", "edit"),))
    assert repo.list_customers(auth, user=u) == []
    assert repo.find_case(auth, tree["ka"].id, user=u) is None


def test_no_user_means_unfiltered(repo, auth, tree):
    """Plan 2's bootstrap and admin maintenance need the whole tenant."""
    assert len(repo.list_customers(auth)) == 2
