"""Creating and revoking an invitation (spec §6): the record, the email
attempt, and what revoking an ACCEPTED one does differently.

`revoke_invitation` composes `users.remove_user` (for an accepted
invite) and `Repository.delete_invite`, and neither swallows
`ConsentRequired` -- both are attended deletes, a human admin present to
approve, the same reasoning `test_repository_users.py` and
`test_repository_invites.py` give their own delete calls. So, exactly
like those modules, a test that wants a REAL removal drives the
in-memory store's consent gate to completion with `approve_all` /
`pre_approve_delete` rather than asking `Repository` to bypass it.
"""
import pytest

from reportbuilder.auth import invites, users
from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired


def approve_all(store, fn):
    """Run *fn*, approving each consent request until it completes.

    Mirrors the identically-named helper in `test_repository_users.py`,
    `test_repository_invites.py` and `test_repository_sessions.py` --
    kept local rather than imported, for the same reason those give.
    """
    for _ in range(50):
        try:
            return fn()
        except ConsentRequired as exc:
            store.approve(exc.request_id)
    raise AssertionError("consent loop did not converge")


def pre_approve_delete(store, auth, path):
    """Register and grant consent for *path* without deleting it yet --
    "this authority is already available", the way it is for nSight's
    own admin bearer in production."""
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


@pytest.fixture
def admin(repo, auth):
    return repo.save_user(auth, User(id="", email="admin@egoiq.com", name="Admin", is_admin=True))


def _fake_sender(calls):
    def _sender(config, to, subject, body):
        calls.append((config, to, subject, body))
        return True
    return _sender


class TestCreateInvitation:
    def test_records_the_invite_with_its_grants(self, repo, auth, admin):
        result = invites.create_invitation(
            repo, auth, email="new@egoiq.com", grants=(Grant("attendo", "view"),),
            invited_by=admin, login_url="https://studio.example.com/login",
            sender=_fake_sender([]))
        assert result.invite.email == "new@egoiq.com"
        assert result.invite.grants == (Grant("attendo", "view"),)
        assert repo.get_invite(auth, result.invite.id) is not None

    def test_emails_when_a_transport_is_configured(self, repo, auth, admin):
        repo.set_setting(auth, "email.json",
                         {"host": "smtp.example.com", "from_addr": "nsight@example.com"})
        calls = []
        result = invites.create_invitation(
            repo, auth, email="new@egoiq.com", grants=(), invited_by=admin,
            login_url="https://studio.example.com/login", sender=_fake_sender(calls))
        assert result.emailed is True
        assert calls[0][1] == "new@egoiq.com"
        assert "https://studio.example.com/login" in calls[0][3]

    def test_the_link_is_studios_own_login_never_datahives(self, repo, auth, admin):
        """The task's own words: "the link to nSight Studio login," not a
        datahive link (spec D5)."""
        result = invites.create_invitation(
            repo, auth, email="new@egoiq.com", grants=(), invited_by=admin,
            login_url="https://studio.example.com/login", sender=_fake_sender([]))
        assert result.link == "https://studio.example.com/login"

    def test_no_transport_configured_is_recorded_but_not_emailed(self, repo, auth, admin):
        """Spec §6: "delivery may fail without failing the invitation" --
        the record exists either way."""
        result = invites.create_invitation(
            repo, auth, email="new@egoiq.com", grants=(), invited_by=admin,
            login_url="https://studio.example.com/login", sender=_fake_sender([]))
        assert result.emailed is False
        assert repo.get_invite(auth, result.invite.id) is not None

    def test_a_failed_send_is_also_not_a_failed_invitation(self, repo, auth, admin):
        repo.set_setting(auth, "email.json",
                         {"host": "smtp.example.com", "from_addr": "nsight@example.com"})
        result = invites.create_invitation(
            repo, auth, email="new@egoiq.com", grants=(), invited_by=admin,
            login_url="https://studio.example.com/login", sender=lambda *a: False)
        assert result.emailed is False
        assert repo.get_invite(auth, result.invite.id) is not None


class TestRevokeInvitation:
    def test_revoking_a_pending_invite_deletes_it(self, repo, auth, admin):
        inv = repo.create_invite(auth, "new@egoiq.com", (), admin.id, lifetime_seconds=3600)
        result = approve_all(repo.store, lambda: invites.revoke_invitation(repo, auth, inv.id))
        assert result is None
        assert repo.get_invite(auth, inv.id) is None

    def test_revoking_an_unknown_invite_is_a_no_op(self, repo, auth):
        assert invites.revoke_invitation(repo, auth, "inv-nope") is None

    def test_revoking_an_accepted_invite_removes_the_user_too(self, repo, auth, admin):
        inv = repo.create_invite(auth, "new@egoiq.com", (Grant("attendo", "edit"),),
                                 admin.id, lifetime_seconds=3600)
        accepted = repo.save_user(auth, User(id="", email="new@egoiq.com",
                                             grants=(Grant("attendo", "edit"),)))
        repo.mark_invite_accepted(auth, inv.id, accepted.id)
        result = approve_all(repo.store, lambda: invites.revoke_invitation(repo, auth, inv.id))
        assert result is None
        assert repo.get_invite(auth, inv.id) is None
        assert repo.get_user(auth, accepted.id) is None

    def test_revoking_an_accepted_invite_still_obeys_the_last_admin_rule(self, repo, auth):
        """Composed from users.remove_user, not reimplemented -- so this
        rule cannot be bypassed by going through "revoke" instead of
        "remove"."""
        inviter = repo.save_user(auth, User(id="", email="inviter@egoiq.com", is_admin=True))
        inv = repo.create_invite(auth, "onlyadmin@egoiq.com", (), inviter.id, lifetime_seconds=3600)
        accepted = repo.save_user(auth, User(id="", email="onlyadmin@egoiq.com", is_admin=True))
        repo.mark_invite_accepted(auth, inv.id, accepted.id)
        approve_all(repo.store, lambda: repo.delete_user(auth, inviter.id))  # now `accepted` is the ONLY admin

        result = invites.revoke_invitation(repo, auth, inv.id)
        assert isinstance(result, users.LastAdminRefused)
        assert repo.get_user(auth, accepted.id) is not None
        assert repo.get_invite(auth, inv.id) is not None

    def test_revoking_an_accepted_invite_also_ends_the_users_sessions(self, repo, auth, admin):
        """`users.remove_user` drops live sessions too (spec §7) -- revoke
        must not leave a session outliving the account it belonged to."""
        inv = repo.create_invite(auth, "new@egoiq.com", (), admin.id, lifetime_seconds=3600)
        accepted = repo.save_user(auth, User(id="", email="new@egoiq.com"))
        repo.mark_invite_accepted(auth, inv.id, accepted.id)
        sid = repo.create_session(auth, accepted.id, lifetime_seconds=3600)
        pre_approve_delete(repo.store, auth, P.session_path(sid.id))
        approve_all(repo.store, lambda: invites.revoke_invitation(repo, auth, inv.id))
        assert repo.get_session(auth, sid.id) is None
