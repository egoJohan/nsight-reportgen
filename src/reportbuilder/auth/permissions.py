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

    def __post_init__(self) -> None:
        """Validate scope and mode. A bad scope is a configuration error (raises);
        a bad path in a request returns False (see covers()).

        Reject:
        - empty scope: Grant("", "edit").covers(x) returns True for any x
          (both want and have[:0] are [], so the prefix check always wins)
        - trailing slash: violates Global Constraints
        - . or .. segments: defence in depth against traversal if datahive's
          _seg() is bypassed
        - mode outside {"view", "edit"}: case-sensitive; "Edit" silently
          degrades to read-only instead of raising
        """
        if not self.scope:
            raise ValueError("scope must not be empty")
        if self.scope.endswith("/"):
            raise ValueError("scope must not have a trailing slash")
        if self.mode not in (VIEW, EDIT):
            raise ValueError(f"mode must be 'view' or 'edit', not {self.mode!r}")

        segments = [s for s in self.scope.split("/") if s]
        if "." in segments or ".." in segments:
            raise ValueError("scope must not contain . or .. segments")

    def covers(self, path: str) -> bool:
        """Does this grant's prefix contain *path*?

        Segment-wise, so "attendo" does not admit "attendo-oy": a path prefix is
        a prefix of the SEGMENTS, not of the string. Reject paths with . or ..
        segments — a hostile path is a request, not a configuration error, so
        return False rather than raise.
        """
        have = [s for s in path.split("/") if s]
        if "." in have or ".." in have:
            return False

        want = [s for s in self.scope.split("/") if s]
        return len(have) >= len(want) and have[: len(want)] == want


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str = ""
    is_admin: bool = False
    grants: tuple[Grant, ...] = field(default_factory=tuple)
    #: When this account last minted a session, ISO-8601, or None for never.
    #: Written in one place — `Repository.record_sign_in`, called where a
    #: session is issued — and never by an ordinary save, so an admin toggling
    #: a flag cannot silently reset it. None is meaningful rather than missing:
    #: an invited person who has not turned up yet reads as "Never", which is
    #: what a separate list of pending invitations used to be for.
    last_login_at: str | None = None


def _depth(scope: str) -> int:
    return len([s for s in scope.split("/") if s])


def _best(user: User, path: str) -> Grant | None:
    """The most specific grant covering *path*, or None.

    Most specific wins, so a view grant on a customer and an edit grant on one
    of its cases mean what they look like they mean.

    Ties are broken towards EDIT, and that matters: two grants on the SAME
    scope are the same depth, so `max` alone returned whichever happened to be
    first in the list, and the answer to "may this person write?" depended on
    the order the grants were stored in. Same user, same grants, different
    answer. `PUT /users/{id}/grants` accepts such a list, so it was reachable
    even though the admin screen merges by scope before sending.

    EDIT wins rather than VIEW because a grant is a capability: holding two on
    one scope means holding both, and the union is what they add up to. The
    security question is settled one level up — nothing here decides WHETHER
    somebody may hold a grant, only what the grants they hold mean together.
    """
    covering = [g for g in user.grants if g.covers(path)]
    if not covering:
        return None
    return max(covering, key=lambda g: (_depth(g.scope), g.mode == EDIT))


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
