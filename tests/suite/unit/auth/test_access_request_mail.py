"""Emailing the people who could decide an access request: who gets
picked (`decision_makers`) and the best-effort send (`notify_decision_makers`).

Same shape as test_invites.py -- a fake `Sender` so no test opens a real
socket, and delivery is proven best-effort (unconfigured or failing is
never an error).
"""
import pytest

from reportbuilder.auth import access_request_mail
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


def _fake_sender(calls):
    def _sender(config, to, subject, body):
        calls.append((to, subject, body))
        return True
    return _sender


def _configure_email(repo, auth):
    repo.set_setting(auth, "email.json",
                     {"host": "smtp.example.com", "from_addr": "nsight@example.com"})


class TestDecisionMakers:
    def test_every_admin_is_included(self, repo, auth):
        admin = repo.save_user(auth, User(id="", email="admin@egoiq.com", is_admin=True))
        requester = repo.save_user(auth, User(id="", email="requester@egoiq.com"))

        out = access_request_mail.decision_makers(
            repo, auth, customer_id="attendo", exclude_user_id=requester.id)
        assert {u.id for u in out} == {admin.id}

    def test_every_edit_holder_on_the_named_customer_is_included(self, repo, auth):
        owner = repo.save_user(auth, User(id="", email="owner@egoiq.com",
                                          grants=(Grant("attendo", "edit"),)))
        requester = repo.save_user(auth, User(id="", email="requester@egoiq.com"))

        out = access_request_mail.decision_makers(
            repo, auth, customer_id="attendo", exclude_user_id=requester.id)
        assert {u.id for u in out} == {owner.id}

    def test_a_view_only_grant_on_the_customer_is_not_included(self, repo, auth):
        repo.save_user(auth, User(id="", email="viewer@egoiq.com",
                                  grants=(Grant("attendo", "view"),)))
        requester = repo.save_user(auth, User(id="", email="requester@egoiq.com"))

        out = access_request_mail.decision_makers(
            repo, auth, customer_id="attendo", exclude_user_id=requester.id)
        assert out == []

    def test_edit_on_a_different_customer_is_not_included(self, repo, auth):
        repo.save_user(auth, User(id="", email="other-owner@egoiq.com",
                                  grants=(Grant("synsam", "edit"),)))
        requester = repo.save_user(auth, User(id="", email="requester@egoiq.com"))

        out = access_request_mail.decision_makers(
            repo, auth, customer_id="attendo", exclude_user_id=requester.id)
        assert out == []

    def test_the_requester_is_excluded_even_when_they_qualify(self, repo, auth):
        """An admin, or an owner, requesting a DIFFERENT customer than the
        one they own is still the requester here -- they filed THIS
        request, so they are excluded from ITS notification regardless of
        what else they hold."""
        admin = repo.save_user(auth, User(id="", email="admin@egoiq.com", is_admin=True,
                                          grants=(Grant("attendo", "edit"),)))
        out = access_request_mail.decision_makers(
            repo, auth, customer_id="attendo", exclude_user_id=admin.id)
        assert out == []

    def test_an_admin_who_also_owns_the_customer_is_one_entry_not_two(self, repo, auth):
        both = repo.save_user(auth, User(id="", email="both@egoiq.com", is_admin=True,
                                         grants=(Grant("attendo", "edit"),)))
        requester = repo.save_user(auth, User(id="", email="requester@egoiq.com"))

        out = access_request_mail.decision_makers(
            repo, auth, customer_id="attendo", exclude_user_id=requester.id)
        assert [u.id for u in out] == [both.id]


class TestNotifyDecisionMakers:
    def test_no_transport_configured_sends_nothing_and_does_not_call_sender(self, repo, auth):
        repo.save_user(auth, User(id="", email="admin@egoiq.com", is_admin=True))
        requester = repo.save_user(auth, User(id="", email="requester@egoiq.com"))
        r = repo.create_access_request(auth, user_id=requester.id, user_email=requester.email,
                                       customer_id="attendo", mode="edit")

        calls = []
        sent = access_request_mail.notify_decision_makers(
            repo, auth, request=r, customer_name="Attendo",
            settings_url="https://studio.example.com/settings?tab=permission-requests",
            sender=_fake_sender(calls))
        assert sent == 0
        assert calls == []

    def test_emails_every_decision_maker_once_configured(self, repo, auth):
        _configure_email(repo, auth)
        admin = repo.save_user(auth, User(id="", email="admin@egoiq.com", is_admin=True))
        owner = repo.save_user(auth, User(id="", email="owner@egoiq.com",
                                          grants=(Grant("attendo", "edit"),)))
        requester = repo.save_user(auth, User(id="", email="requester@egoiq.com"))
        r = repo.create_access_request(auth, user_id=requester.id, user_email=requester.email,
                                       customer_id="attendo", mode="edit")

        calls = []
        sent = access_request_mail.notify_decision_makers(
            repo, auth, request=r, customer_name="Attendo",
            settings_url="https://studio.example.com/settings?tab=permission-requests",
            sender=_fake_sender(calls))
        assert sent == 2
        assert {to for to, _subject, _body in calls} == {admin.email, owner.email}

    def test_the_requester_never_receives_this_email(self, repo, auth):
        """Even when the requester is themselves an admin -- they already
        know what they just did."""
        _configure_email(repo, auth)
        requester = repo.save_user(auth, User(id="", email="admin@egoiq.com", is_admin=True))
        r = repo.create_access_request(auth, user_id=requester.id, user_email=requester.email,
                                       customer_id="attendo", mode="edit")

        calls = []
        sent = access_request_mail.notify_decision_makers(
            repo, auth, request=r, customer_name="Attendo",
            settings_url="https://studio.example.com/settings?tab=permission-requests",
            sender=_fake_sender(calls))
        assert sent == 0
        assert calls == []

    def test_a_failed_send_is_not_raised_and_is_not_counted(self, repo, auth):
        _configure_email(repo, auth)
        repo.save_user(auth, User(id="", email="admin@egoiq.com", is_admin=True))
        requester = repo.save_user(auth, User(id="", email="requester@egoiq.com"))
        r = repo.create_access_request(auth, user_id=requester.id, user_email=requester.email,
                                       customer_id="attendo", mode="edit")

        sent = access_request_mail.notify_decision_makers(
            repo, auth, request=r, customer_name="Attendo",
            settings_url="https://studio.example.com/settings?tab=permission-requests",
            sender=lambda *a: False)
        assert sent == 0

    def test_the_body_names_who_what_and_where_to_decide_it(self, repo, auth):
        _configure_email(repo, auth)
        repo.save_user(auth, User(id="", email="admin@egoiq.com", is_admin=True))
        requester = repo.save_user(auth, User(id="", email="viewer@egoiq.com"))
        r = repo.create_access_request(auth, user_id=requester.id, user_email=requester.email,
                                       customer_id="attendo", mode="edit")

        calls = []
        access_request_mail.notify_decision_makers(
            repo, auth, request=r, customer_name="Attendo",
            settings_url="https://studio.example.com/settings?tab=permission-requests",
            sender=_fake_sender(calls))
        _to, _subject, body = calls[0]
        assert "viewer@egoiq.com" in body
        assert "edit" in body
        assert "Attendo" in body
        assert "https://studio.example.com/settings?tab=permission-requests" in body
        # Nothing sensitive: no token, no session id -- just a link that
        # requires signing in to act on.
        assert "token" not in body.lower()
        assert "session" not in body.lower()
