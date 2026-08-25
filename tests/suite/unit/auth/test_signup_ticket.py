"""The ticket that proves an identity and grants nothing.

The single most important property is the last test: a signup ticket must not
be readable as a session, and a session must not be readable as a ticket. If
either held, a stranger who authenticated with a provider would have an account
— which is the thing this codebase removed passwords to prevent.
"""
from __future__ import annotations

import pytest

from reportbuilder.auth import session, signup_ticket

KEY = b"k" * 32
pytestmark = pytest.mark.unit


def test_a_ticket_round_trips_what_the_provider_vouched_for():
    t = signup_ticket.issue(KEY, email="Alice@Customer.com", provider="google",
                            name="Alice")
    assert signup_ticket.read_ticket(KEY, t) == {
        "email": "alice@customer.com", "provider": "google", "name": "Alice"}


def test_a_ticket_signed_with_another_key_is_not_read():
    t = signup_ticket.issue(KEY, email="a@x.com", provider="google")
    assert signup_ticket.read_ticket(b"j" * 32, t) is None


def test_rubbish_is_not_read():
    for junk in ("", "not-a-ticket", "a.b.c"):
        assert signup_ticket.read_ticket(KEY, junk) is None


def test_a_ticket_without_an_email_is_not_read():
    """A ticket that names nobody authorises nothing."""
    forged = signup_ticket._codec(KEY).dumps({"provider": "google"})
    assert signup_ticket.read_ticket(KEY, forged) is None


def test_a_session_cookie_is_not_a_ticket_and_a_ticket_is_not_a_session():
    """Enforced by the salt, not by naming. This is the property that keeps a
    verified stranger from holding an account."""
    ticket = signup_ticket.issue(KEY, email="a@x.com", provider="google")
    cookie = session.cookie_value(KEY, "sess-1")

    assert session.session_id_from_cookie(KEY, ticket) is None
    assert signup_ticket.read_ticket(KEY, cookie) is None
