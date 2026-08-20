"""A verified email -> a User, or a refusal. Every sign-in method (password,
Google, Microsoft) ends here with nothing but the email — see the plan's
Task 4.
"""
import pytest

from reportbuilder.auth.identity import SignInRefused, resolve_signed_in_user
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


def test_a_known_user_is_returned_as_is(repo, auth):
    repo.save_user(auth, User(id="", email="maija@egoiq.com", name="Maija",
                              grants=(Grant("attendo", "edit"),)))
    got = resolve_signed_in_user(repo, auth, "maija@egoiq.com", frozenset())
    assert isinstance(got, User) and got.name == "Maija"


def test_email_matching_is_case_insensitive(repo, auth):
    repo.save_user(auth, User(id="", email="maija@egoiq.com", name="Maija"))
    got = resolve_signed_in_user(repo, auth, "Maija@Egoiq.com", frozenset())
    assert isinstance(got, User) and got.email == "maija@egoiq.com"


def test_the_first_bootstrap_admin_is_created_with_no_grants(repo, auth):
    got = resolve_signed_in_user(repo, auth, "admin@egoiq.com", frozenset({"admin@egoiq.com"}))
    assert isinstance(got, User)
    assert got.is_admin is True
    assert got.grants == ()


def test_bootstrap_is_ignored_once_any_user_exists(repo, auth):
    repo.save_user(auth, User(id="", email="someone@egoiq.com"))
    got = resolve_signed_in_user(repo, auth, "admin@egoiq.com", frozenset({"admin@egoiq.com"}))
    assert isinstance(got, SignInRefused)


def test_an_email_not_in_bootstrap_is_refused_on_an_empty_hive(repo, auth):
    got = resolve_signed_in_user(repo, auth, "nobody@egoiq.com", frozenset({"admin@egoiq.com"}))
    assert isinstance(got, SignInRefused)


def test_domain_auto_join_creates_a_user_with_default_grants(repo, auth):
    repo.set_setting(auth, "access.json",
                     {"allowed_domains": ["egoiq.com"],
                      "default_grants": [{"scope": "attendo", "mode": "view"}]})
    got = resolve_signed_in_user(repo, auth, "new@egoiq.com", frozenset())
    assert isinstance(got, User)
    assert got.is_admin is False
    assert got.grants == (Grant("attendo", "view"),)


def test_domain_auto_join_may_grant_nothing(repo, auth):
    repo.set_setting(auth, "access.json", {"allowed_domains": ["egoiq.com"], "default_grants": []})
    got = resolve_signed_in_user(repo, auth, "new@egoiq.com", frozenset())
    assert isinstance(got, User) and got.grants == ()


def test_an_unlisted_domain_is_refused(repo, auth):
    repo.set_setting(auth, "access.json", {"allowed_domains": ["egoiq.com"], "default_grants": []})
    got = resolve_signed_in_user(repo, auth, "new@example.com", frozenset())
    assert isinstance(got, SignInRefused)


def test_no_access_json_at_all_refuses_rather_than_crashing(repo, auth):
    got = resolve_signed_in_user(repo, auth, "new@example.com", frozenset())
    assert isinstance(got, SignInRefused)


def test_not_an_email_is_refused(repo, auth):
    got = resolve_signed_in_user(repo, auth, "not-an-email", frozenset())
    assert isinstance(got, SignInRefused)


def test_domain_auto_join_does_not_reactivate_bootstrap(repo, auth):
    """A hive with one real user is no longer "empty" even if that user came
    from domain auto-join, not the bootstrap path."""
    repo.set_setting(auth, "access.json", {"allowed_domains": ["egoiq.com"], "default_grants": []})
    resolve_signed_in_user(repo, auth, "first@egoiq.com", frozenset())
    got = resolve_signed_in_user(repo, auth, "admin@other.com", frozenset({"admin@other.com"}))
    assert isinstance(got, SignInRefused)
