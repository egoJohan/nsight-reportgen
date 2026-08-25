"""Proof that somebody authenticated, and holds nothing.

There is a moment, after Google or Microsoft has vouched for an email and
before nSight has any account for it, when we know exactly who somebody is and
owe them nothing. `identity.resolve_signed_in_user` returns `SignInRefused`
there and the sign-in ends — which is correct, and is also the moment at which
that person is most able to say "then let me ask".

This is the smallest thing that lets them ask: a signed, short-lived ticket
naming the verified email and the provider that verified it. It authorises ONE
action, filing a signup request, and nothing else.

**It is not a session and must never be mistaken for one.** A different cookie
name, a different salt, and — the part that matters — no path from here into
`current_user`. If this ticket could satisfy that dependency it would be an
account, minted from an email a stranger presented, which is exactly the class
of thing that was just removed from this codebase. The salt is what enforces
it cryptographically: a session cookie handed to `read_ticket` fails to
deserialise, and a ticket handed to `session_id_from_cookie` fails likewise,
because `itsdangerous` binds the signature to the salt.

Fifteen minutes. Long enough to read a page and press a button, short enough
that a ticket left in a shared browser is worthless by the time anyone finds
it. It carries no id and is never stored: nothing to revoke, because it grants
nothing to revoke.
"""
from __future__ import annotations

import itsdangerous

COOKIE_NAME = "nsight_signup"

#: Long enough to read the page and decide; short enough to be worthless if
#: left behind. Refreshing means signing in with the provider again, which is
#: no hardship and re-proves the thing the ticket asserts.
LIFETIME_SECONDS = 15 * 60

#: DIFFERENT from session's `nsight-session-cookie-v1`. This is the mechanism
#: that stops the two being interchangeable — not a naming convention.
_SALT = "nsight-signup-ticket-v1"


def _codec(signing_key: bytes) -> itsdangerous.URLSafeTimedSerializer:
    return itsdangerous.URLSafeTimedSerializer(signing_key, salt=_SALT)


def issue(signing_key: bytes, *, email: str, provider: str, name: str = "") -> str:
    """A ticket asserting *email* was verified by *provider*."""
    return _codec(signing_key).dumps(
        {"email": (email or "").strip().lower(), "provider": provider, "name": name})


def read_ticket(signing_key: bytes, cookie: str) -> dict | None:
    """What the ticket asserts, or None if it is absent, malformed, signed with
    a different key or salt, or older than its lifetime.

    Returns None rather than raising: an unreadable ticket is an anonymous
    caller, which every caller here already knows how to answer.
    """
    if not cookie:
        return None
    try:
        value = _codec(signing_key).loads(cookie, max_age=LIFETIME_SECONDS)
    except itsdangerous.BadData:
        return None
    if not isinstance(value, dict):
        return None
    email = str(value.get("email") or "").strip().lower()
    provider = str(value.get("provider") or "")
    if not email or "@" not in email or not provider:
        return None
    return {"email": email, "provider": provider, "name": str(value.get("name") or "")}
