"""The tenant grant a domain carries is evaluated, not stored.

A domain's mode has to reach the colleagues who ALREADY have accounts —
that is the whole reason the setting exists. Johan's ask was "everyone with
an nSight address may edit everything, then narrow where needed", and every
one of those people signed in months ago. Stamping the grant onto the
account at first sign-in would reach only people who join afterwards, and
would leave the grant behind when the admin later takes the domain away.

So `effective_user` reads the setting on each session resolve and adds the
grant to the user it hands back. The stored account never carries it: what
an admin sees on the Users screen stays the list of grants they gave.
(Johan, 2026-09-10)
"""
from __future__ import annotations

import pytest

from reportbuilder.auth.identity import effective_user
from reportbuilder.auth.permissions import ALL_SCOPE, EDIT, VIEW, Grant, User, \
    may_read, may_write
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

CUSTOMER = "cus-abc"


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


def configure(repo, auth, access=(), *, sign_in=()):
    """*access* is the tenant-wide grant list, *sign_in* the admission list.
    Two settings, because they are two questions -- see test_domain_access.py."""
    repo.set_setting(auth, "access.json",
                     {"allowed_domains": list(sign_in), "domain_access": list(access)})


def test_an_account_that_predates_the_setting_gets_the_tenant_grant(repo, auth):
    """The case the feature is for: the colleague already has an account and
    no grants, and the admin has just said "this domain may edit everything"."""
    old = repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija"))
    assert not may_read(old, CUSTOMER)

    configure(repo, auth, [{"domain": "nsight.fi", "mode": EDIT}])
    assert may_write(effective_user(repo, auth, old), CUSTOMER)


def test_taking_the_domain_away_takes_the_access_away(repo, auth):
    user = repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija"))
    configure(repo, auth, [{"domain": "nsight.fi", "mode": VIEW}])
    assert may_read(effective_user(repo, auth, user), CUSTOMER)

    configure(repo, auth, [])
    assert not may_read(effective_user(repo, auth, user), CUSTOMER)


def test_the_grant_is_never_written_onto_the_account(repo, auth):
    """An admin's Users screen must keep showing the grants they gave, not a
    tenant grant nobody typed there — and a stored copy would outlive the
    setting it came from."""
    user = repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija"))
    configure(repo, auth, [{"domain": "nsight.fi", "mode": EDIT}])
    effective_user(repo, auth, user)
    assert repo.get_user(auth, user.id).grants == ()


def test_a_grant_on_one_customer_still_narrows_the_tenant(repo, auth):
    """This is how an admin restricts somebody: the more specific grant wins,
    which is what the Domains screen tells them."""
    user = repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija",
                                     grants=(Grant(CUSTOMER, VIEW),)))
    configure(repo, auth, [{"domain": "nsight.fi", "mode": EDIT}])
    seen = effective_user(repo, auth, user)
    assert may_read(seen, CUSTOMER)
    assert not may_write(seen, CUSTOMER)
    assert may_write(seen, "cus-other")


def test_another_domain_is_untouched(repo, auth):
    user = repo.save_user(auth, User(id="", email="ext@elsewhere.com", name="Ext"))
    configure(repo, auth, [{"domain": "nsight.fi", "mode": EDIT}])
    assert not may_read(effective_user(repo, auth, user), CUSTOMER)


def test_being_allowed_to_sign_in_grants_nothing_by_itself(repo, auth):
    user = repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija"))
    configure(repo, auth, sign_in=["nsight.fi"])
    assert not may_read(effective_user(repo, auth, user), CUSTOMER)


def test_an_unreadable_setting_leaves_the_user_as_they_were(repo, auth):
    """The setting lives in the hive. If it cannot be read, the answer is the
    account's own grants — never a tenant grant invented from nothing, and
    never a crash on the sign-in path."""
    user = repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija",
                                     grants=(Grant(CUSTOMER, VIEW),)))
    assert effective_user(repo, auth, user).grants == (Grant(CUSTOMER, VIEW),)


def test_an_admin_is_handed_back_unchanged(repo, auth):
    admin = repo.save_user(auth, User(id="", email="boss@nsight.fi", name="Boss",
                                      is_admin=True))
    configure(repo, auth, [{"domain": "nsight.fi", "mode": EDIT}])
    assert effective_user(repo, auth, admin).is_admin


def test_the_tenant_grant_shows_up_in_the_resolved_session(repo, auth):
    """Through the real seam: `session.resolve` is what every request uses."""
    from reportbuilder.auth import session as _session
    _session._cache = _session._Cache()
    user = repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija"))
    configure(repo, auth, [{"domain": "nsight.fi", "mode": EDIT}])
    sid = _session.create(repo, auth, user.id)
    try:
        assert may_write(_session.resolve(repo, auth, sid), CUSTOMER)
    finally:
        _session._cache = _session._Cache()


def test_the_tenant_grant_covers_a_path_under_a_customer(repo, auth):
    """`*` is depth 0, so it must still admit the nested paths the store
    addresses — a report lives at `cus-…/case-…/rep-…`."""
    user = repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija"))
    configure(repo, auth, [{"domain": "nsight.fi", "mode": VIEW}])
    assert may_read(effective_user(repo, auth, user), f"{CUSTOMER}/case-1/rep-2")


def test_renaming_yourself_does_not_write_the_tenant_grant_onto_the_account(repo, auth):
    """`PATCH /me` saves the request's user, which carries the tenant grant.
    Written through, the grant would outlive the setting that produced it and
    show up on the admin's Users screen as a grant nobody gave.

    Guarded structurally: the grant lives on its own field, so a save that
    writes `grants` cannot carry it.
    """
    from dataclasses import replace as _replace
    user = repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija"))
    configure(repo, auth, [{"domain": "nsight.fi", "mode": EDIT}])
    seen = effective_user(repo, auth, user)

    repo.save_user(auth, _replace(seen, first_name="Maija", last_name="M", name=""))
    assert repo.get_user(auth, user.id).grants == ()


def test_the_users_own_grants_are_what_an_admin_sees(repo, auth):
    user = repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija",
                                     grants=(Grant(CUSTOMER, VIEW),)))
    configure(repo, auth, [{"domain": "nsight.fi", "mode": EDIT}])
    assert effective_user(repo, auth, user).grants == (Grant(CUSTOMER, VIEW),)


def test_a_listing_filter_sees_the_tenant_scope(repo, auth):
    """`visible_scopes` is the cheap path used to filter listings; it must
    agree with `may_read` or a tenant-granted user gets an empty Home."""
    from reportbuilder.auth.permissions import visible_scopes
    user = repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija"))
    configure(repo, auth, [{"domain": "nsight.fi", "mode": VIEW}])
    assert ALL_SCOPE in visible_scopes(effective_user(repo, auth, user))


def test_access_without_admission_grants_but_does_not_let_anyone_in(repo, auth):
    """The independence the split is for: a partner whose people are all
    invited by hand is still owed access to everything, and that must not
    become a way to sign up unsolicited."""
    from reportbuilder.auth.identity import SignInRefused, resolve_signed_in_user
    configure(repo, auth, [{"domain": "partner.com", "mode": VIEW}])   # no sign_in

    invited = repo.save_user(auth, User(id="", email="ext@partner.com", name="Ext"))
    assert may_read(effective_user(repo, auth, invited), CUSTOMER)

    stranger = resolve_signed_in_user(repo, auth, "nobody@partner.com",
                                      frozenset(), email_domain_proven=True)
    assert isinstance(stranger, SignInRefused)


def test_admission_without_access_lets_people_in_with_nothing(repo, auth):
    """The other half. This is also every deployment that configured a domain
    before access lists existed -- they must not have gained anything."""
    from reportbuilder.auth.identity import resolve_signed_in_user
    configure(repo, auth, sign_in=["nsight.fi"])

    joined = resolve_signed_in_user(repo, auth, "new@nsight.fi",
                                    frozenset(), email_domain_proven=True)
    assert isinstance(joined, User)
    assert not may_read(effective_user(repo, auth, joined), CUSTOMER)
