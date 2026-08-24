"""What makes a stored deck stale.

`render_key` fingerprints everything a render depends on, and the download
button hands back the stored deck whenever the key still matches. The template
was missing from it. The report JSON carries only the report's OWN explicit
template choice, which is usually empty — a template is normally inherited from
the tutkimus, the customer, or the house default — so changing any of those
left the key exactly where it was. Every report already rendered kept being
handed its deck in the old template, with the UI saying it was current.
"""
from __future__ import annotations

import pytest

from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def world():
    auth = AuthContext(token="t")
    repo = Repository(InMemoryObjectStore())
    cust = repo.create_customer(auth, "Asiakas")
    case = repo.create_case(auth, cust.id, "Tutkimus")
    mat = repo.attach_material(auth, cust.id, case.id, "s.sav", b"data")
    rep = repo.save_report(auth, cust.id, case.id, '{"name":"R","charts":[]}')
    return repo, auth, cust.id, case.id, rep.id, mat.id


def _key(world):
    repo, auth, cust, case, rid, mid = world
    return repo.render_key(auth, cust, case, rid, mid)


def test_changing_the_customers_template_makes_the_deck_stale(world):
    repo, auth, cust, case, rid, _mid = world
    before = _key(world)

    tid = repo.upload_template(auth, cust, "Uusi",
                               b"PK\x03\x04 a different template").id
    repo.set_template(auth, tid, customer_id=cust)

    assert _key(world) != before, "the stored deck is still in the old template"


def test_replacing_the_house_default_file_makes_it_stale(world):
    """The id that hides it: the house default is the literal string "default"
    however many different files pass through it, so keying on the id alone
    meant replacing the tenant's default changed nothing anybody could see."""
    repo, auth, _cust, _case, _rid, _mid = world
    repo.store.put(auth, P.default_template_path(), b"PK\x03\x04 first",
                   "application/vnd.openxmlformats-officedocument.presentationml.presentation")
    before = _key(world)

    repo.store.put(auth, P.default_template_path(), b"PK\x03\x04 second, quite different",
                   "application/vnd.openxmlformats-officedocument.presentationml.presentation")

    assert _key(world) != before


def test_nothing_changing_keeps_the_deck_current(world):
    """The other half. A key that moves on its own would re-render every deck
    on every check, which is minutes of LibreOffice per report."""
    assert _key(world) == _key(world)


def test_an_unresolvable_template_does_not_break_the_key(world):
    """A render must not fail over styling: without a template it falls back to
    the house style, and the key has to keep working."""
    repo, auth, cust, case, rid, mid = world
    assert repo.resolved_template_identity(auth, cust, case, rid).startswith("template:")
    assert repo.render_key(auth, cust, case, rid, mid)
