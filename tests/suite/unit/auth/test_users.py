"""Removing and demoting users, and the last-admin rule that guards both
(spec §5): "the last admin cannot be removed or demoted."

`InMemoryObjectStore` gates every first delete on a path behind a consent
request, unconditionally (floor rule 4). In production nSight talks to its
own hive under an admin bearer, so `remove_user`'s calls into
`Repository.delete_user`/`delete_sessions_for_user` never actually block on
that gate; the double still models it faithfully, so tests that want to
observe a REAL removal drive the gate the same way
`tests/suite/unit/store/test_repository_sessions.py` does: `approve_all` for
the paths `delete_user` itself raises on (it does not swallow
`ConsentRequired` -- see its call site in `users.remove_user`), and
`pre_approve_delete` for the session path, because `delete_session` swallows
its own `ConsentRequired` and so never gives `approve_all` anything to catch.
"""
import pytest

from reportbuilder.auth import users
from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired


def approve_all(store, fn):
    """Run *fn*, approving each consent request until it completes.

    Mirrors `test_repository_sessions.py`'s helper of the same name -- kept
    local rather than imported, for the same reason it gives.
    """
    for _ in range(50):
        try:
            return fn()
        except ConsentRequired as exc:
            store.approve(exc.request_id)
    raise AssertionError("consent loop did not converge")


def pre_approve_delete(store, auth, path):
    """Register and grant consent for *path* without deleting it yet -- "this
    authority is already available", the way it is for nSight's own admin
    bearer in production (see this module's docstring)."""
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


def _make(repo, auth, email, *, admin=False, grants=()):
    return repo.save_user(auth, User(id="", email=email, name=email.split("@")[0],
                                     is_admin=admin, grants=grants))


class TestRemoveUser:
    def test_removes_an_ordinary_user(self, repo, auth):
        u = _make(repo, auth, "a@x.c", grants=(Grant("attendo", "edit"),))
        result = approve_all(repo.store, lambda: users.remove_user(repo, auth, u.id))
        assert result is None
        assert repo.get_user(auth, u.id) is None

    def test_removes_the_users_live_sessions_too(self, repo, auth):
        """Spec §7: deleting a user ends their session -- immediately here,
        not waiting on the idle timeout to catch up."""
        u = _make(repo, auth, "a@x.c")
        sid = repo.create_session(auth, u.id, lifetime_seconds=3600)
        pre_approve_delete(repo.store, auth, P.session_path(sid.id))
        approve_all(repo.store, lambda: users.remove_user(repo, auth, u.id))
        assert repo.get_session(auth, sid.id) is None

    def test_refuses_to_remove_the_last_admin(self, repo, auth):
        u = _make(repo, auth, "only-admin@x.c", admin=True)
        result = users.remove_user(repo, auth, u.id)
        assert isinstance(result, users.LastAdminRefused)
        assert repo.get_user(auth, u.id) is not None

    def test_removes_an_admin_when_another_admin_remains(self, repo, auth):
        _make(repo, auth, "keeps@x.c", admin=True)
        u = _make(repo, auth, "goes@x.c", admin=True)
        result = approve_all(repo.store, lambda: users.remove_user(repo, auth, u.id))
        assert result is None
        assert repo.get_user(auth, u.id) is None

    def test_removing_an_unknown_user_is_a_no_op(self, repo, auth):
        assert users.remove_user(repo, auth, "usr-nope") is None

    def test_removes_the_users_password_too(self, repo, auth):
        """No orphaned credential material left behind once the account
        itself is gone -- see `Repository.delete_user`'s docstring."""
        u = _make(repo, auth, "a@x.c")
        repo.set_password(auth, u.id, "some-hash")
        approve_all(repo.store, lambda: users.remove_user(repo, auth, u.id))
        assert repo.get_password_hash(auth, u.id) is None


class TestSetAdmin:
    def test_promotes_an_ordinary_user(self, repo, auth):
        u = _make(repo, auth, "a@x.c")
        result = users.set_admin(repo, auth, u.id, True)
        assert isinstance(result, User) and result.is_admin is True

    def test_refuses_to_demote_the_last_admin(self, repo, auth):
        u = _make(repo, auth, "only-admin@x.c", admin=True)
        result = users.set_admin(repo, auth, u.id, False)
        assert isinstance(result, users.LastAdminRefused)
        assert repo.get_user(auth, u.id).is_admin is True

    def test_demotes_one_of_two_admins(self, repo, auth):
        _make(repo, auth, "keeps@x.c", admin=True)
        u = _make(repo, auth, "goes@x.c", admin=True)
        result = users.set_admin(repo, auth, u.id, False)
        assert isinstance(result, User) and result.is_admin is False

    def test_demoting_preserves_grants(self, repo, auth):
        _make(repo, auth, "keeps@x.c", admin=True)
        u = _make(repo, auth, "goes@x.c", admin=True, grants=(Grant("attendo", "view"),))
        users.set_admin(repo, auth, u.id, False)
        assert repo.get_user(auth, u.id).grants == (Grant("attendo", "view"),)

    def test_setting_admin_on_an_unknown_user_is_none(self, repo, auth):
        assert users.set_admin(repo, auth, "usr-nope", True) is None
