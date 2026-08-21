"""Invitations, stored in datahive (spec §6, §9): an admin adds someone by
email, and this record is what "pending" / "accepted" MEANS.

`delete_invite` does not swallow `ConsentRequired` -- revoking is a
deliberate, attended deletion of a credential, the same as
`users.remove_user`'s `delete_user` call (see both docstrings), unlike
`delete_session`'s unattended cleanup. So, exactly as
`tests/suite/unit/store/test_repository_users.py` does for `delete_user`,
a test that needs a REAL removal drives the in-memory store's consent gate
to completion with `approve_all` rather than asking `Repository` to bypass it.
"""
import pytest

from reportbuilder.auth.permissions import Grant
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired


def approve_all(store, fn):
    """Run *fn*, approving each consent request until it completes.

    Mirrors the identically-named helper in `test_repository_sessions.py`
    and `test_repository_users.py` -- kept local rather than imported,
    since importing test helpers across test modules is its own kind of
    coupling.
    """
    for _ in range(50):
        try:
            return fn()
        except ConsentRequired as exc:
            store.approve(exc.request_id)
    raise AssertionError("consent loop did not converge")


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


def test_a_created_invite_comes_back_whole(repo, auth):
    inv = repo.create_invite(auth, "Maija@Egoiq.com", (Grant("attendo", "view"),),
                             "usr-admin", lifetime_seconds=3600)
    assert inv.id and inv.email == "maija@egoiq.com"  # normalized, like find_user_by_email
    got = repo.get_invite(auth, inv.id)
    assert got.grants == (Grant("attendo", "view"),)
    assert got.invited_by == "usr-admin"
    assert got.accepted_user_id is None


def test_an_unknown_invite_id_is_none_not_an_error(repo, auth):
    assert repo.get_invite(auth, "inv-nope") is None


def test_listing_returns_every_invite_newest_first(repo, auth):
    first = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=3600)
    second = repo.create_invite(auth, "b@x.c", (), "admin", lifetime_seconds=3600)
    assert [i.id for i in repo.list_invites(auth)] == [second.id, first.id]


def test_a_pending_invite_is_found_by_email(repo, auth):
    inv = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=3600)
    found = repo.find_pending_invite_by_email(auth, "A@X.C")
    assert found is not None and found.id == inv.id


def test_an_accepted_invite_is_no_longer_pending(repo, auth):
    inv = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=3600)
    repo.mark_invite_accepted(auth, inv.id, "usr-1")
    assert repo.find_pending_invite_by_email(auth, "a@x.c") is None
    got = repo.get_invite(auth, inv.id)
    assert got.accepted_user_id == "usr-1" and got.accepted_at


def test_an_expired_invite_is_not_pending(repo, auth):
    inv = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=-1)
    assert repo.find_pending_invite_by_email(auth, "a@x.c") is None
    # Still readable directly -- expiry only changes whether sign-in matches it.
    assert repo.get_invite(auth, inv.id) is not None


def test_deleting_an_invite_removes_it(repo, auth):
    inv = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=3600)
    approve_all(repo.store, lambda: repo.delete_invite(auth, inv.id))
    assert repo.get_invite(auth, inv.id) is None


def test_deleting_an_invite_needing_consent_does_not_raise(repo, auth):
    """The propagating contract, from the caller's side: with no consent
    granted, `delete_invite` raises rather than pretending the credential
    is gone -- see its docstring for why that differs from
    `delete_session`."""
    inv = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=3600)
    with pytest.raises(ConsentRequired):
        repo.delete_invite(auth, inv.id)


def test_deleting_an_unknown_invite_does_nothing(repo, auth):
    repo.delete_invite(auth, "inv-nope")  # no raise


def test_marking_an_unknown_invite_accepted_does_nothing(repo, auth):
    repo.mark_invite_accepted(auth, "inv-nope", "usr-1")  # no raise


def test_invite_ids_are_unguessable_tokens(repo, auth):
    """The id is also the lookup token (P.invite_path's docstring): it must
    not be a short, brute-forceable value like the other entities'
    uuid4-derived ids."""
    inv = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=3600)
    assert inv.id.startswith("inv-")
    assert len(inv.id) > 30
