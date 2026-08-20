"""Sessions, stored in datahive so a revoked or expired one is the same fact
everywhere (spec §7) — never in the process alone.

`InMemoryObjectStore` gates every first delete on a path behind a consent
request, unconditionally, mirroring datahive's floor rule 4. In production
nSight talks to its own hive under an admin bearer specifically so a
destructive call like `delete_session` never actually blocks on that gate
(`scripts/dev-stack.sh`); the in-memory double still models the gate faithfully
because that's what makes an out-of-caveat or unapproved delete fail here
rather than in production. `approve_all` stands in for that admin authority —
"consent already available" — so tests that need to observe a REAL removal
drive the gate to completion instead of asking `Repository` to bypass it.
`delete_session` itself, deliberately, never surfaces that gate (see its
docstring) — the tests for that behaviour don't use `approve_all` at all.
"""
import pytest

from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired


def approve_all(store, fn):
    """Run *fn*, approving each consent request until it completes.

    Mirrors `tests/suite/unit/store/test_repository.py`'s helper of the same
    name — kept local rather than imported, since this file is about sessions
    specifically and importing test helpers across test modules is its own
    kind of coupling.
    """
    for _ in range(50):
        try:
            return fn()
        except ConsentRequired as exc:
            store.approve(exc.request_id)
    raise AssertionError("consent loop did not converge")


def pre_approve_delete(store, auth, path):
    """Register and grant consent for *path* without deleting it yet — "this
    authority is already available", the way it is for nSight's own admin
    bearer in production. A later delete of this exact path, from anywhere,
    then just succeeds with no exception at all: not `delete_session`
    swallowing one, but the store never raising one in the first place.
    """
    try:
        store.delete(auth, path)
    except ConsentRequired as exc:
        store.approve(exc.request_id)
    else:
        raise AssertionError("expected ConsentRequired on a fresh path")


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


def test_a_created_session_can_be_read_back(repo, auth):
    s = repo.create_session(auth, "usr-1", lifetime_seconds=3600)
    assert s.id and s.user_id == "usr-1"
    got = repo.get_session(auth, s.id)
    assert got is not None and got.user_id == "usr-1"
    assert got.created == got.last_seen == s.created


def test_an_unknown_session_id_is_none_not_an_error(repo, auth):
    assert repo.get_session(auth, "sess-nope") is None


def test_an_expired_session_reads_as_absent(repo, auth):
    """The safety net `delete_session`'s docstring leans on: a session is
    unusable the moment it expires, whether or not anything ever managed to
    delete the record."""
    s = repo.create_session(auth, "usr-1", lifetime_seconds=-1)
    assert repo.get_session(auth, s.id) is None


def test_touch_updates_last_seen_only(repo, auth):
    s = repo.create_session(auth, "usr-1", lifetime_seconds=3600)
    repo.touch_session(auth, s.id, "2030-01-01T00:00:00+00:00")
    got = repo.get_session(auth, s.id)
    assert got.last_seen == "2030-01-01T00:00:00+00:00"
    assert got.created == s.created and got.expires == s.expires


def test_touching_an_unknown_session_does_nothing(repo, auth):
    repo.touch_session(auth, "sess-nope", "2030-01-01T00:00:00+00:00")  # no raise


def test_deleting_a_session_ends_it(repo, auth):
    """Exercises the store's consent behaviour directly: with consent granted
    — the normal case in production, where nSight's admin bearer already has
    the authority a human would otherwise have to give — a session really is
    gone once deleted, not just unraised-upon."""
    s = repo.create_session(auth, "usr-1", lifetime_seconds=3600)
    approve_all(repo.store, lambda: repo.store.delete(auth, P.session_path(s.id)))
    assert repo.get_session(auth, s.id) is None


def test_deleting_a_session_that_needs_consent_does_not_raise(repo, auth):
    """The tolerant contract, exercising `delete_session` itself: sign-out and
    idle/expiry cleanup (`auth/session.py`) run with no human present to
    answer a consent prompt, so this must never raise — even though the
    in-memory double would gate the underlying delete on first attempt. See
    `Repository.delete_session`'s docstring for why that's safe."""
    s = repo.create_session(auth, "usr-1", lifetime_seconds=3600)
    repo.delete_session(auth, s.id)  # no raise, consent never granted


def test_deleting_an_unknown_session_does_nothing(repo, auth):
    repo.delete_session(auth, "sess-nope")  # no raise


def test_delete_sessions_for_user_takes_only_theirs(repo, auth):
    """Consent for *a*'s session is granted up front — "already available",
    as it is for nSight's own admin bearer in production — so this proves
    `delete_sessions_for_user`'s own filtering, not just that it avoids
    raising: only usr-a's record is targeted and only it disappears."""
    a = repo.create_session(auth, "usr-a", lifetime_seconds=3600)
    b = repo.create_session(auth, "usr-b", lifetime_seconds=3600)
    pre_approve_delete(repo.store, auth, P.session_path(a.id))
    repo.delete_sessions_for_user(auth, "usr-a")
    assert repo.get_session(auth, a.id) is None
    assert repo.get_session(auth, b.id) is not None


def test_delete_sessions_for_user_never_raises_without_consent(repo, auth):
    """The tolerant contract again, this time through the cascade: deleting a
    user's sessions is exactly as unattended as deleting one directly, so it
    must not raise even though nothing pre-approved anything here."""
    repo.create_session(auth, "usr-a", lifetime_seconds=3600)
    repo.delete_sessions_for_user(auth, "usr-a")  # no raise
