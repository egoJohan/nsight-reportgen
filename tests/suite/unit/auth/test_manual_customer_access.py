"""A customer can manage its own access, ignoring the domain policy.

"The customer needs to control specific customer access manually." The Domains
screen answers one question for the whole tenant — everyone at nsight.fi may
edit everything — and that is the right default for most work and exactly wrong
for the one customer whose data a subset of people may see.

So a customer is either INHERIT, which respects the domain setting as it always
has, or MANUAL, which takes nothing from it: only the people an admin named on
the customer itself may reach it.

Manual withholds DERIVED access only. A grant an admin gave by name still
admits, which is what makes this a narrowing of the domain policy rather than a
second, competing way to refuse somebody — and it is why the owner, who is given
an explicit edit grant when they create the customer, keeps working there.
(Johan, 2026-09-14)
"""
from __future__ import annotations

import pytest

from reportbuilder.auth.identity import (
    CUSTOMER_ACCESS_KEY, MANUAL, effective_user,
)
from reportbuilder.auth.permissions import (
    ALL_SCOPE, EDIT, VIEW, Grant, User, may_read, may_write,
)
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

OPEN = "cus-open"
CLOSED = "cus-closed"


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


def configure(repo, auth, *, domain_mode=EDIT, manual=()):
    repo.set_setting(auth, "access.json",
                     {"allowed_domains": [],
                      "domain_access": [{"domain": "nsight.fi", "mode": domain_mode}]})
    repo.set_setting(auth, CUSTOMER_ACCESS_KEY,
                     {"modes": {cid: MANUAL for cid in manual}})


def maija(repo, auth, grants=()):
    return repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija",
                                     grants=tuple(grants)))


def test_a_manual_customer_is_invisible_to_the_domain_grant(repo, auth):
    """The point of the feature: the domain says "edit everything", and this
    one customer is not part of everything."""
    user = maija(repo, auth)
    configure(repo, auth, manual=[CLOSED])
    seen = effective_user(repo, auth, user)

    assert may_write(seen, OPEN), "an inheriting customer is untouched"
    assert not may_read(seen, CLOSED), "a manual customer takes nothing from the domain"


def test_a_grant_given_by_name_still_admits(repo, auth):
    """Manual withholds what was DERIVED, never what an admin gave."""
    user = maija(repo, auth, grants=[Grant(CLOSED, VIEW)])
    configure(repo, auth, manual=[CLOSED])
    seen = effective_user(repo, auth, user)

    assert may_read(seen, CLOSED)
    assert not may_write(seen, CLOSED), "the named grant is view, and view is what they get"


def test_the_owners_explicit_edit_grant_survives(repo, auth):
    """Creating a customer writes `Grant(cid, EDIT)` onto the creator, so the
    owner keeps working in what they made whatever the mode says."""
    user = maija(repo, auth, grants=[Grant(CLOSED, EDIT)])
    configure(repo, auth, manual=[CLOSED])

    assert may_write(effective_user(repo, auth, user), CLOSED)


def test_everything_under_a_manual_customer_is_denied_too(repo, auth):
    """A study and a report live beneath the customer; denying the customer and
    admitting its contents would be no denial at all."""
    user = maija(repo, auth)
    configure(repo, auth, manual=[CLOSED])
    seen = effective_user(repo, auth, user)

    assert not may_read(seen, f"{CLOSED}/case-1")
    assert not may_read(seen, f"{CLOSED}/case-1/rep-2")


def test_a_similarly_named_customer_is_not_caught(repo, auth):
    """Segment-wise, like `Grant.covers`: "cus-closed" must not deny
    "cus-closed-oy", which is a different customer."""
    user = maija(repo, auth)
    configure(repo, auth, manual=[CLOSED])

    assert may_write(effective_user(repo, auth, user), f"{CLOSED}-oy")


def test_inherit_is_the_default_for_every_customer_that_predates_this(repo, auth):
    """No setting at all means the tenant behaves exactly as it did."""
    user = maija(repo, auth)
    repo.set_setting(auth, "access.json",
                     {"allowed_domains": [],
                      "domain_access": [{"domain": "nsight.fi", "mode": EDIT}]})

    assert may_write(effective_user(repo, auth, user), CLOSED)


def test_naming_a_customer_inherit_changes_nothing(repo, auth):
    user = maija(repo, auth)
    repo.set_setting(auth, "access.json",
                     {"allowed_domains": [],
                      "domain_access": [{"domain": "nsight.fi", "mode": EDIT}]})
    repo.set_setting(auth, CUSTOMER_ACCESS_KEY, {"modes": {CLOSED: "inherit"}})

    assert may_write(effective_user(repo, auth, user), CLOSED)


def test_the_tenant_grant_still_covers_a_customer_nobody_has_heard_of(repo, auth):
    """`*` admits paths the store has never seen — that contract is what stops
    a customer created mid-request from being refused."""
    user = maija(repo, auth)
    configure(repo, auth, manual=[CLOSED])

    assert may_write(effective_user(repo, auth, user), "cus-invented-just-now")


def test_the_setting_still_shows_up_in_visible_scopes(repo, auth):
    """The cheap listing filter keeps returning `*`; the per-path check is what
    withholds a manual customer, and `_admits` asks that per path."""
    from reportbuilder.auth.permissions import visible_scopes
    user = maija(repo, auth)
    configure(repo, auth, manual=[CLOSED])

    assert ALL_SCOPE in visible_scopes(effective_user(repo, auth, user))


def test_an_unreadable_setting_denies_nothing_new(repo, auth):
    """It cannot be read, so nothing is named manual, so nothing is withheld —
    and a user's own grants are untouched either way."""
    user = maija(repo, auth, grants=[Grant(OPEN, VIEW)])
    assert effective_user(repo, auth, user).grants == (Grant(OPEN, VIEW),)


def test_the_mode_is_never_written_onto_the_account(repo, auth):
    """Like the tenant grant: it describes a setting, not the person."""
    user = maija(repo, auth)
    configure(repo, auth, manual=[CLOSED])
    effective_user(repo, auth, user)

    assert repo.get_user(auth, user.id).grants == ()
