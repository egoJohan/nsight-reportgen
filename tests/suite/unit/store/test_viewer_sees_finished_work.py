"""A view-only grant is the client's grant.

Handing a client the working state of a deck nobody has finished shows them
half-built slides, numbers mid-edit and titles still being written — and
invites comment on all of it. The distinction already existed everywhere else:
the case page badges a report "Generated" once a render is stamped on it, and
the download button refuses without one. Only the report list and the report
itself ignored it.

Whoever BUILDS the report sees it at every stage, obviously. This is about who
receives it.
"""
from __future__ import annotations

import pytest

from reportbuilder.auth.permissions import EDIT, VIEW, Grant, User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.repository_client import RepositoryClient
from reportbuilder.store.seam import AuthContext, NotFound


@pytest.fixture
def world():
    """A case with one finished deck and one still being built."""
    auth = AuthContext(token="t")
    repo = Repository(InMemoryObjectStore())
    cust = repo.create_customer(auth, "Asiakas")
    case = repo.create_case(auth, cust.id, "Tutkimus")
    done = repo.save_report(auth, cust.id, case.id, '{"name":"Valmis","charts":[]}')
    wip = repo.save_report(auth, cust.id, case.id, '{"name":"Kesken","charts":[]}')
    repo.save_render(auth, cust.id, case.id, done.id, b"deck", "valmis.pptx")
    return repo, auth, cust.id, case.id, done.id, wip.id


def _client(repo, auth, cust, case, mode):
    user = User(id="u", email="u@example.com", name="U",
                grants=(Grant(scope=f"{cust}/{case}", mode=mode),))
    return RepositoryClient(repo, auth, user)


def test_a_viewer_is_shown_only_the_finished_deck(world):
    repo, auth, cust, case, done, wip = world
    listed = _client(repo, auth, cust, case, VIEW).list_reports(case)
    assert [r["report_id"] for r in listed] == [done]


def test_an_editor_is_shown_everything(world):
    repo, auth, cust, case, done, wip = world
    listed = _client(repo, auth, cust, case, EDIT).list_reports(case)
    assert {r["report_id"] for r in listed} == {done, wip}


def test_a_viewer_cannot_open_an_unfinished_report_by_its_id(world):
    """Hiding it from the list is not enough — the id is in the URL, and a
    report someone linked to before it was finished is the obvious way in."""
    repo, auth, cust, case, done, wip = world
    client = _client(repo, auth, cust, case, VIEW)
    with pytest.raises(NotFound):
        client.load_report(case, wip)
    assert "Valmis" in client.load_report(case, done)


def test_an_editor_can_open_the_unfinished_one(world):
    repo, auth, cust, case, done, wip = world
    assert "Kesken" in _client(repo, auth, cust, case, EDIT).load_report(case, wip)


def test_an_internal_caller_with_no_user_still_sees_everything(world):
    """Render, export and the AI passes run with no request behind them."""
    repo, auth, cust, case, done, wip = world
    client = RepositoryClient(repo, auth, None)
    assert {r["report_id"] for r in client.list_reports(case)} == {done, wip}
    assert "Kesken" in client.load_report(case, wip)


def test_editing_a_delivered_report_does_not_take_it_back_from_the_client(world):
    """Delivering is not undone by editing.

    A save clears `render_key` on purpose — that is how the app says the stored
    deck no longer matches the report, and it is what the Generated badge and
    the download button read. Gating the viewer on that same flag meant a client
    lost sight of a deck already delivered to them the moment an analyst touched
    a title. What they see is the deck that exists; that the next version is not
    ready yet is the analyst's business.
    """
    repo, auth, cust, case, done, _wip = world
    client = _client(repo, auth, cust, case, VIEW)
    assert [r["report_id"] for r in client.list_reports(case)] == [done]

    repo.save_report(auth, cust, case, '{"name":"Valmis, muokattu","charts":[]}',
                     report_id=done)

    assert [r["report_id"] for r in client.list_reports(case)] == [done]
    assert "Valmis" in client.load_report(case, done)


def test_a_report_that_was_never_rendered_stays_out_of_sight(world):
    """The other half — the rule still has to mean something."""
    repo, auth, cust, case, _done, wip = world
    repo.save_report(auth, cust, case, '{"name":"Kesken 2","charts":[]}',
                     report_id=wip)
    client = _client(repo, auth, cust, case, VIEW)
    assert wip not in {r["report_id"] for r in client.list_reports(case)}
