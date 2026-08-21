"""Cookie <-> session id <-> User, and the 30 s cache spec §7 requires.
"""
from datetime import datetime, timedelta, timezone

import itsdangerous
import pytest

from reportbuilder.auth import session
from reportbuilder.auth.permissions import User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired


def approve_all(store, fn):
    """Run *fn*, approving each consent request until it completes.

    `InMemoryObjectStore` gates every first delete behind a consent request,
    unconditionally (mirrors datahive's floor rule 4). `repo.delete_user` —
    unlike `repo.delete_session` — does NOT swallow that gate (deleting a
    user is a real, attended admin action), so a test that needs a user
    ACTUALLY gone drives the gate to completion here, matching the pattern
    in `tests/suite/unit/store/test_repository_users.py`.
    """
    for _ in range(50):
        try:
            return fn()
        except ConsentRequired as exc:
            store.approve(exc.request_id)
    raise AssertionError("consent loop did not converge")


@pytest.fixture(autouse=True)
def _reset_cache():
    """The cache is module-level and shared across tests without this."""
    session._cache = session._Cache()
    yield
    session._cache = session._Cache()


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def user(repo, auth):
    return repo.save_user(auth, User(id="", email="maija@egoiq.com", name="Maija"))


@pytest.fixture
def key():
    return b"0" * 32


class TestCookieCodec:
    def test_a_cookie_round_trips_the_session_id(self, key):
        cookie = session.cookie_value(key, "sess-abc")
        assert session.session_id_from_cookie(key, cookie) == "sess-abc"

    def test_tampering_is_rejected(self, key):
        """Tamper with the PAYLOAD, not the last character of the signature.

        The old version flipped the final character, which is the one place a
        flip can be a no-op: base64url without padding leaves spare bits in the
        last character, so two spellings can decode to identical signature
        bytes. The cookie string changed, the credential did not, and the test
        failed at random. Verified exhaustively: flipping any character of the
        payload or timestamp is always rejected (14490/14490).
        """
        cookie = session.cookie_value(key, "sess-abc")
        payload, rest = cookie.split(".", 1)
        forged = payload[:-1] + ("y" if payload[-1] != "y" else "z")
        assert session.session_id_from_cookie(key, f"{forged}.{rest}") is None

    def test_a_cookie_signed_with_a_different_key_is_rejected(self, key):
        cookie = session.cookie_value(key, "sess-abc")
        assert session.session_id_from_cookie(b"1" * 32, cookie) is None

    def test_garbage_is_rejected_not_raised(self, key):
        assert session.session_id_from_cookie(key, "not-a-cookie") is None

    def test_a_cookie_older_than_the_absolute_lifetime_is_rejected(self, key):
        old = itsdangerous.URLSafeTimedSerializer(key, salt=session._SALT)
        cookie = old.dumps("sess-abc")
        # loads() checks the signature's OWN timestamp against max_age; a
        # negative max_age is the cheapest way to force "already too old"
        # without waiting real time out.
        assert session.session_id_from_cookie(key, cookie) is not None  # sanity: fresh is fine
        import time
        real_time = time.time
        try:
            time.time = lambda: real_time() + session.ABSOLUTE_LIFETIME_SECONDS + 1
            assert session.session_id_from_cookie(key, cookie) is None
        finally:
            time.time = real_time


class TestCreateAndResolve:
    def test_a_created_session_resolves_to_its_user(self, repo, auth, user):
        sid = session.create(repo, auth, user.id)
        resolved = session.resolve(repo, auth, sid)
        assert resolved is not None and resolved.id == user.id

    def test_an_unknown_session_id_resolves_to_none(self, repo, auth):
        assert session.resolve(repo, auth, "sess-nope") is None

    def test_a_revoked_session_resolves_to_none_immediately(self, repo, auth, user):
        sid = session.create(repo, auth, user.id)
        assert session.resolve(repo, auth, sid) is not None
        session.revoke(repo, auth, sid)
        assert session.resolve(repo, auth, sid) is None

    def test_a_deleted_users_session_resolves_to_none(self, repo, auth, user):
        sid = session.create(repo, auth, user.id)
        approve_all(repo.store, lambda: repo.delete_user(auth, user.id))
        assert session.resolve(repo, auth, sid) is None


class TestExpiry:
    def test_past_the_absolute_lifetime_is_dead(self, repo, auth, user, monkeypatch):
        sid = session.create(repo, auth, user.id)
        stale = repo.get_session(auth, sid)
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
        repo._write_json(auth, __import__("reportbuilder.store.paths", fromlist=["session_path"])
                         .session_path(sid),
                         {"id": stale.id, "user_id": stale.user_id, "created": stale.created,
                          "last_seen": stale.last_seen, "expires": expired},
                         ["nsight:session"])
        assert session.resolve(repo, auth, sid) is None

    def test_idle_past_the_timeout_is_dead(self, repo, auth, user):
        sid = session.create(repo, auth, user.id)
        stale = repo.get_session(auth, sid)
        long_idle = (datetime.now(timezone.utc)
                    - timedelta(seconds=session.IDLE_TIMEOUT_SECONDS + 1)).isoformat(timespec="seconds")
        repo.touch_session(auth, sid, long_idle)
        assert session.resolve(repo, auth, sid) is None


class TestRevocationCache:
    """Spec §7: resolution is cached for CACHE_TTL_SECONDS, so a revocation or
    a deleted user takes effect within that window, not instantly, UNLESS the
    revocation went through `session.revoke` on the same process."""

    def test_a_cache_hit_does_not_re_read_the_store(self, repo, auth, user, monkeypatch):
        sid = session.create(repo, auth, user.id)
        session.resolve(repo, auth, sid)  # warms the cache

        def _boom(*a, **k):
            raise AssertionError("should not read the store on a cache hit")
        monkeypatch.setattr(repo, "get_session", _boom)
        assert session.resolve(repo, auth, sid) is not None

    def test_revoke_evicts_the_cache_immediately(self, repo, auth, user):
        sid = session.create(repo, auth, user.id)
        session.resolve(repo, auth, sid)  # warms the cache
        session.revoke(repo, auth, sid)
        assert session.resolve(repo, auth, sid) is None

    def test_a_stale_cache_entry_expires_on_its_own(self, repo, auth, user, monkeypatch):
        sid = session.create(repo, auth, user.id)
        session.resolve(repo, auth, sid)
        import time
        real_monotonic = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: real_monotonic() + session.CACHE_TTL_SECONDS + 1)
        # Deleting the user proves the NEXT resolve re-reads the store rather
        # than serving the stale cached User.
        approve_all(repo.store, lambda: repo.delete_user(auth, user.id))
        assert session.resolve(repo, auth, sid) is None


class TestForgetUser:
    """`forget_user` is the escape hatch from the TTL for a grant change the
    user must see at once — the customer they just created, in their own
    sidebar."""

    def test_a_forgotten_users_next_resolve_re_reads_their_grants(
        self, repo, auth, user
    ):
        from reportbuilder.auth.permissions import Grant

        sid = session.create(repo, auth, user.id)
        assert session.resolve(repo, auth, sid).grants == ()  # warms the cache

        repo.set_grants(auth, user.id, (Grant("cust-new", "edit"),))
        # Still the cached identity: the grant is in the store, unseen.
        assert session.resolve(repo, auth, sid).grants == ()

        session.forget_user(user.id)
        assert [(g.scope, g.mode) for g in session.resolve(repo, auth, sid).grants] == [
            ("cust-new", "edit")
        ]

    def test_forgetting_one_user_leaves_another_users_session_alone(
        self, repo, auth, user, monkeypatch
    ):
        other = repo.save_user(auth, User(id="", email="other@example.com",
                                          name="Other"))
        mine, theirs = (session.create(repo, auth, user.id),
                        session.create(repo, auth, other.id))
        session.resolve(repo, auth, mine)
        session.resolve(repo, auth, theirs)

        session.forget_user(user.id)

        def _boom(*a, **k):
            raise AssertionError("the other session's cache entry was dropped")
        monkeypatch.setattr(repo, "get_session", _boom)
        assert session.resolve(repo, auth, theirs) is not None

    def test_forgetting_a_user_does_not_resurrect_a_revoked_session(
        self, repo, auth, user
    ):
        """A tombstone outlives forget_user on purpose: `delete_session` can be
        blocked by the consent gate, so the tombstone IS sign-out."""
        sid = session.create(repo, auth, user.id)
        session.resolve(repo, auth, sid)
        session.revoke(repo, auth, sid)

        session.forget_user(user.id)

        assert session.resolve(repo, auth, sid) is None
