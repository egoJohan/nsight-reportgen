"""A grant that covers the whole tenant, and what still overrides it.

Access was per-customer, so "everyone who works here may see everything" had to
be written out customer by customer and re-written whenever a customer was
added: "käyttöoikeudet on vain omiin raportteihin, tulee aika paljon oikeuksien
määrittelyä". The missing piece was a scope meaning ALL of it.

Its depth is what makes it safe to hand out. `_best` picks the MOST SPECIFIC
grant covering a path, so a tenant grant — depth 0 — loses to any grant naming
an actual customer. That is what "give everyone edit, restrict where needed"
rests on: a narrower grant beats the blanket one rather than adding to it.
(Johan, 2026-09-10)
"""
from __future__ import annotations

import pytest

from reportbuilder.auth.permissions import (
    ALL_SCOPE, Grant, User, may_read, may_write,
)


def _user(*grants: tuple[str, str]) -> User:
    return User(id="u", email="a@nsight.fi",
                grants=tuple(Grant(s, m) for s, m in grants))


def test_a_tenant_grant_covers_any_customer():
    u = _user((ALL_SCOPE, "view"))
    assert may_read(u, "cust-abc")
    assert may_read(u, "cust-abc/case-1/report/rep-9")


def test_view_on_the_tenant_is_not_write():
    u = _user((ALL_SCOPE, "view"))
    assert may_read(u, "cust-abc")
    assert not may_write(u, "cust-abc")


def test_edit_on_the_tenant_writes_anywhere():
    u = _user((ALL_SCOPE, "edit"))
    assert may_write(u, "cust-abc/case-1")


def test_a_named_customer_overrides_the_blanket_grant():
    """The restriction rule: tenant EDIT, but read-only on one customer."""
    u = _user((ALL_SCOPE, "edit"), ("cust-secret", "view"))
    assert may_write(u, "cust-open")
    assert may_read(u, "cust-secret")
    assert not may_write(u, "cust-secret"), "the narrower grant must win"


def test_it_still_cannot_reach_a_reserved_path():
    """Settings and users are app configuration, not tenant data — a blanket
    data grant must not open them."""
    u = _user((ALL_SCOPE, "edit"))
    from reportbuilder.auth.permissions import _RESERVED

    for head in _RESERVED:
        assert not may_read(u, f"{head}/anything"), head
        assert not may_write(u, f"{head}/anything"), head


def test_a_hostile_path_is_still_refused():
    u = _user((ALL_SCOPE, "edit"))
    assert not may_read(u, "cust-a/../settings")


def test_the_empty_scope_is_still_rejected():
    """`*` is the ONE way to say "everything" — an empty scope stays a
    configuration error, so nothing gets it by accident."""
    with pytest.raises(ValueError):
        Grant("", "edit")


def test_a_customer_literally_named_star_cannot_be_confused_with_it():
    """`*` is not a path segment any id can take: ids are minted as
    `cust-<hex>`, so this is defence in depth rather than a live case."""
    u = _user(("cust-star", "edit"))
    assert not may_read(u, "cust-other")
