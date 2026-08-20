"""Who may see what.

nSight holds a datahive token that is read-write across the whole tenant (spec
D3), so datahive no longer filters anything per user. These two functions are
the only thing separating one customer's data from another's — treat changes
here as security changes.

A grant is a datahive PATH PREFIX plus a mode:

    Grant("attendo",            "edit")   the customer and everything under it
    Grant("attendo/case-9b32",  "view")   one study, without its customer

which are Speksi 2's P-O-05 and P-O-06/07 expressed as data rather than as a
token caveat.
"""
from __future__ import annotations

from dataclasses import dataclass, field

VIEW = "view"
EDIT = "edit"

#: Objects under this prefix are app configuration — users, grants, fonts,
#: templates settings. They are reached through the admin dependency, never
#: through a data grant, or a grant named "settings" would be an escalation.
_RESERVED = ("settings",)


@dataclass(frozen=True)
class Grant:
    scope: str
    mode: str = VIEW

    def covers(self, path: str) -> bool:
        """Does this grant's prefix contain *path*?

        Segment-wise, so "attendo" does not admit "attendo-oy": a path prefix is
        a prefix of the SEGMENTS, not of the string.
        """
        want = [s for s in self.scope.split("/") if s]
        have = [s for s in path.split("/") if s]
        return len(have) >= len(want) and have[: len(want)] == want


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str = ""
    is_admin: bool = False
    grants: tuple[Grant, ...] = field(default_factory=tuple)


def _best(user: User, path: str) -> Grant | None:
    """The most specific grant covering *path*, or None.

    Most specific wins, so a view grant on a customer and an edit grant on one
    of its cases mean what they look like they mean.
    """
    covering = [g for g in user.grants if g.covers(path)]
    if not covering:
        return None
    return max(covering, key=lambda g: len([s for s in g.scope.split("/") if s]))


def _reserved(path: str) -> bool:
    head = next((s for s in path.split("/") if s), "")
    return head in _RESERVED


def may_read(user: User, path: str) -> bool:
    if _reserved(path):
        return False
    return _best(user, path) is not None


def may_write(user: User, path: str) -> bool:
    if _reserved(path):
        return False
    grant = _best(user, path)
    return grant is not None and grant.mode == EDIT


def visible_scopes(user: User) -> tuple[str, ...]:
    """The scopes this user may see, for filtering a listing cheaply."""
    return tuple(g.scope for g in user.grants)
