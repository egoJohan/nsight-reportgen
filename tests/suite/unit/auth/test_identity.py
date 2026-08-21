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


class TestEmailDomainProven:
    """Task 12c: multi-tenant Microsoft sign-in can hand this function an
    email whose DOMAIN ownership is not proven (see oidc.py's module
    docstring on `xms_edov`). An unproven email may resolve to an account
    that already exists, but must never mint a new one -- whether via
    domain auto-join or the bootstrap-admin path, both of which are ways
    of trusting a self-asserted email to create an account nobody vetted."""

    def test_an_unproven_email_still_resolves_an_existing_user(self, repo, auth):
        repo.save_user(auth, User(id="", email="maija@egoiq.com", name="Maija"))
        got = resolve_signed_in_user(repo, auth, "maija@egoiq.com", frozenset(),
                                     email_domain_proven=False)
        assert isinstance(got, User) and got.email == "maija@egoiq.com"

    def test_an_unproven_email_is_refused_for_an_unknown_user_even_on_an_allowed_domain(
            self, repo, auth):
        repo.set_setting(auth, "access.json",
                         {"allowed_domains": ["egoiq.com"], "default_grants": []})
        got = resolve_signed_in_user(repo, auth, "new@egoiq.com", frozenset(),
                                     email_domain_proven=False)
        assert isinstance(got, SignInRefused)

    def test_an_unproven_email_cannot_become_the_bootstrap_admin(self, repo, auth):
        got = resolve_signed_in_user(repo, auth, "admin@egoiq.com",
                                     frozenset({"admin@egoiq.com"}),
                                     email_domain_proven=False)
        assert isinstance(got, SignInRefused)

    def test_a_proven_email_still_auto_joins_as_before(self, repo, auth):
        repo.set_setting(auth, "access.json",
                         {"allowed_domains": ["egoiq.com"], "default_grants": []})
        got = resolve_signed_in_user(repo, auth, "new@egoiq.com", frozenset(),
                                     email_domain_proven=True)
        assert isinstance(got, User)

    def test_email_domain_proven_defaults_to_true(self, repo, auth):
        """Password sign-in and every other pre-existing caller never passed
        this parameter -- it must keep behaving exactly as before."""
        repo.set_setting(auth, "access.json",
                         {"allowed_domains": ["egoiq.com"], "default_grants": []})
        got = resolve_signed_in_user(repo, auth, "new@egoiq.com", frozenset())
        assert isinstance(got, User)
