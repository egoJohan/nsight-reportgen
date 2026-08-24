"""The sign-in failure counter."""
from __future__ import annotations

import pytest

from reportbuilder.auth.ratelimit import RateLimiter


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock():
    return _Clock()


@pytest.fixture
def limiter(clock):
    return RateLimiter(limit=3, window=60.0, clock=clock)


def test_it_allows_attempts_up_to_the_limit(limiter):
    for _ in range(3):
        assert limiter.allows("a")
        limiter.record_failure("a")
    assert not limiter.allows("a")


def test_the_window_expires_on_its_own(limiter, clock):
    for _ in range(3):
        limiter.record_failure("a")
    assert not limiter.allows("a")
    clock.t += 61
    assert limiter.allows("a"), "no unlock to request, no state to clear by hand"


def test_one_key_does_not_bar_another(limiter):
    for _ in range(3):
        limiter.record_failure("a")
    assert limiter.allows("b")


def test_signing_in_successfully_forgets_the_failures(limiter):
    """Otherwise someone who fumbles their password twice and then gets it
    right carries those two around for the next quarter of an hour."""
    limiter.record_failure("a")
    limiter.record_failure("a")
    limiter.clear("a")
    for _ in range(3):
        assert limiter.allows("a")
        limiter.record_failure("a")


def test_it_says_how_long_to_wait(limiter, clock):
    for _ in range(3):
        limiter.record_failure("a")
    clock.t += 20
    assert 39 <= limiter.retry_after("a") <= 41


def test_it_does_not_grow_without_bound(clock):
    """The key is an email or an address — something the attacker picks. A
    counter that keeps one entry per value invented is itself the attack."""
    limiter = RateLimiter(limit=3, window=60.0, clock=clock)
    limiter.MAX_KEYS = 50
    for i in range(500):
        limiter.record_failure(f"key-{i}")
    assert len(limiter._hits) <= 50
    # And it forgets the OLDEST, so whoever is knocking right now is still
    # counted — evicting the newest would make the bound the way through it.
    assert "key-499" in limiter._hits
    assert "key-0" not in limiter._hits


def test_merely_asking_does_not_create_an_entry(clock):
    """Reading used to insert, while only recording evicted.

    So once an address was blocked, every further request added a permanent key
    and returned 429 without ever reaching the eviction path — the bound was
    never consulted, and the map grew for as long as an attacker cared to send
    requests. Cheap to drive: a refusal costs them no password hash.
    """
    limiter = RateLimiter(limit=3, window=60.0, clock=clock)
    for i in range(500):
        limiter.allows(f"never-seen-{i}")
        limiter.retry_after(f"never-seen-{i}")
    assert limiter._hits == {}


def test_a_key_whose_window_has_passed_stops_being_tracked(clock):
    limiter = RateLimiter(limit=3, window=60.0, clock=clock)
    limiter.record_failure("a")
    assert "a" in limiter._hits
    clock.t += 61
    assert limiter.allows("a")
    assert "a" not in limiter._hits
