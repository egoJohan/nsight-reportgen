"""Asking for an account after a provider has vouched for you.

The dead end this closes: an invitation-only product refuses somebody who
belongs here, and their only recourse is out-of-band email. The thing it must
NOT do is become a way in without an admin — so the tests that matter most
here are the negative ones. A request is a row in a queue; until an admin acts,
the person who filed it can do exactly what they could before.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth import signup_ticket
from reportbuilder.auth.keys import get_or_create_signing_key
from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.integration


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="test")


@pytest.fixture
def anon(repo, auth):
    """A caller with no account and no session."""
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    return TestClient(app)


@pytest.fixture
def admin_client(repo, auth):
    app = create_app()
    admin = repo.save_user(auth, User(id="", email="admin@egoiq.com",
                                      name="Admin", is_admin=True))
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = lambda: admin
    return TestClient(app)


def _with_ticket(client, repo, auth, email="alice@customer.com", provider="google"):
    key = get_or_create_signing_key(repo, auth)
    client.cookies.set(signup_ticket.COOKIE_NAME,
                       signup_ticket.issue(key, email=email, provider=provider,
                                           name="Alice"))
    return client


# --- what a ticket does, and does not, let you do --------------------------

def test_without_a_ticket_nothing_can_be_filed(anon):
    assert anon.post("/signup-requests").status_code == 401
    assert anon.get("/signup/me").status_code == 401


def test_a_ticket_files_a_request_for_its_own_address(anon, repo, auth):
    _with_ticket(anon, repo, auth)
    r = anon.post("/signup-requests")
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "alice@customer.com"
    assert r.json()["state"] == "pending"


def test_the_body_cannot_name_a_different_address(anon, repo, auth):
    """There is no field for it. The identity is the provider's assertion,
    never anything the caller sends."""
    _with_ticket(anon, repo, auth, email="alice@customer.com")
    anon.post("/signup-requests", json={"email": "admin@egoiq.com"})
    [row] = repo.list_signup_requests(auth)
    assert row.email == "alice@customer.com"


def test_a_request_grants_nothing(anon, repo, auth):
    """The whole safety property: filing is not access."""
    _with_ticket(anon, repo, auth)
    anon.post("/signup-requests")
    assert anon.get("/customers").status_code == 401
    assert anon.get("/auth/me").status_code == 401
    assert repo.find_user_by_email(auth, "alice@customer.com") is None


def test_a_session_cookie_is_not_a_ticket(anon, repo, auth):
    """Belt and braces over the salt separation in test_signup_ticket.py."""
    from reportbuilder.auth import session

    key = get_or_create_signing_key(repo, auth)
    user = repo.save_user(auth, User(id="", email="someone@egoiq.com"))
    sid = session.create(repo, auth, user.id)
    anon.cookies.set(signup_ticket.COOKIE_NAME, session.cookie_value(key, sid))
    assert anon.post("/signup-requests").status_code == 401


def test_asking_twice_leaves_one_row(anon, repo, auth):
    _with_ticket(anon, repo, auth)
    anon.post("/signup-requests")
    anon.post("/signup-requests")
    assert len(repo.list_signup_requests(auth)) == 1


def test_someone_who_already_has_an_account_is_told_so(anon, repo, auth):
    repo.save_user(auth, User(id="", email="alice@customer.com"))
    _with_ticket(anon, repo, auth)
    assert anon.post("/signup-requests").status_code == 409


# --- the admin's side ------------------------------------------------------

def test_the_queue_is_admin_only(anon, repo, auth):
    _with_ticket(anon, repo, auth)
    anon.post("/signup-requests")
    assert anon.get("/signup-requests").status_code == 401


def test_approving_creates_the_account_with_the_chosen_grants(
    anon, admin_client, repo, auth
):
    _with_ticket(anon, repo, auth)
    rid = anon.post("/signup-requests").json()["id"]

    r = admin_client.post(f"/signup-requests/{rid}/approve",
                          json={"grants": [{"scope": "attendo", "mode": "edit"}]})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "approved"

    u = repo.find_user_by_email(auth, "alice@customer.com")
    assert u is not None, "approval goes through create_invitation, which creates it"
    assert [(g.scope, g.mode) for g in u.grants] == [("attendo", "edit")]


def test_approving_twice_is_refused(anon, admin_client, repo, auth):
    _with_ticket(anon, repo, auth)
    rid = anon.post("/signup-requests").json()["id"]
    admin_client.post(f"/signup-requests/{rid}/approve", json={"grants": []})
    assert admin_client.post(f"/signup-requests/{rid}/approve",
                             json={"grants": []}).status_code == 409


def test_refusing_removes_the_row_and_creates_no_account(
    anon, admin_client, repo, auth
):
    """A refused stranger is not a decision worth keeping for ever. Removing
    the row also lets them ask again, which is the right answer when the
    refusal was "not yet" or a misclick."""
    _with_ticket(anon, repo, auth)
    rid = anon.post("/signup-requests").json()["id"]
    assert admin_client.delete(f"/signup-requests/{rid}").status_code == 204
    assert repo.find_user_by_email(auth, "alice@customer.com") is None
    assert admin_client.get("/signup-requests").json() == []


def test_a_refused_asker_can_ask_again(anon, admin_client, repo, auth):
    _with_ticket(anon, repo, auth)
    rid = anon.post("/signup-requests").json()["id"]
    admin_client.delete(f"/signup-requests/{rid}")
    assert anon.post("/signup-requests").status_code == 201


# --- the four states the request page has to tell apart --------------------

def test_case_1_a_stranger_is_told_they_may_ask(anon, repo, auth):
    _with_ticket(anon, repo, auth)
    me = anon.get("/signup/me").json()
    assert me["email"] == "alice@customer.com"
    assert me["has_account"] is False and me["pending"] is False


def test_case_2_an_invited_person_is_told_to_sign_in(anon, admin_client, repo, auth):
    """They hold a ticket from before an admin invited them. There is nothing
    to ask for — the account is waiting."""
    _with_ticket(anon, repo, auth)
    admin_client.post("/users/invite",
                      json={"email": "alice@customer.com", "grants": []})
    me = anon.get("/signup/me").json()
    assert me["has_account"] is True
    assert anon.post("/signup-requests").status_code == 409


def test_case_3_an_asker_who_already_asked_is_told_it_is_pending(anon, repo, auth):
    _with_ticket(anon, repo, auth)
    anon.post("/signup-requests")
    me = anon.get("/signup/me").json()
    assert me["pending"] is True and me["has_account"] is False


def test_approval_reports_whether_the_invitation_was_emailed(
    anon, admin_client, repo, auth
):
    """The asker was told they would hear by email. An admin whose SMTP is not
    configured has to know they must say so themselves."""
    _with_ticket(anon, repo, auth)
    rid = anon.post("/signup-requests").json()["id"]
    r = admin_client.post(f"/signup-requests/{rid}/approve", json={"grants": []})
    assert r.json()["emailed"] is False   # no settings/email.json in this test
    assert r.json()["link"].endswith("/login")


def test_an_approved_request_carries_no_grants_the_admin_did_not_choose(
    anon, admin_client, repo, auth
):
    """An empty grants list is a real answer: the account exists, sees nothing,
    and an admin can grant later from the Users screen."""
    _with_ticket(anon, repo, auth)
    rid = anon.post("/signup-requests").json()["id"]
    admin_client.post(f"/signup-requests/{rid}/approve", json={"grants": []})
    u = repo.find_user_by_email(auth, "alice@customer.com")
    assert u.grants == ()
    assert u.is_admin is False
