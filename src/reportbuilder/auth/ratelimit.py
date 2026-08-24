"""A fixed-window failure counter, for the sign-in routes.

`POST /auth/login/password` runs an Argon2 verification on every request —
deliberately expensive, which is the point of Argon2 and also what makes an
unlimited endpoint an amplifier: a few hundred requests a second cost the
attacker nothing and cost this container every core it has. And an endpoint
that will answer a password guess for ever is a password guesser's endpoint.

Deliberately small:

* In process. This deployment runs ONE backend container, so a shared store
  would be ceremony around a dict. If nSight is ever run with replicas, this
  becomes per-replica and the limits want dividing — noted here rather than
  discovered later.
* Failures only. A person typing the right password is never counted, so
  nobody is locked out of their own account by using it.
* A window, not a lockout. It expires on its own; there is no unlock to
  request and no state to clear by hand.
"""
from __future__ import annotations

import time
from collections import OrderedDict, deque


class RateLimiter:
    """`limit` failures per `window` seconds, per key.

    `clock` is injectable so the tests can age a window without sleeping
    through it.
    """

    #: Keys tracked at once. A limiter keyed by anything an attacker chooses —
    #: an email, an address — grows as fast as they can invent values, so it is
    #: bounded and evicts the least recently touched. Eviction can only ever
    #: forget a failure, i.e. err towards letting a request through.
    MAX_KEYS = 10_000

    def __init__(self, limit: int, window: float, clock=time.monotonic) -> None:
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def _live(self, key: str, *, create: bool = False) -> deque[float]:
        """This key's failures inside the window.

        `create=False` — every read — must NOT insert. Reading used to, while
        only `record_failure` evicted, so once an address was blocked every
        further request added a permanent key and returned 429 without ever
        reaching the eviction path: the bound was never consulted and the map
        grew for as long as an attacker cared to send requests.
        """
        now = self._clock()
        hits = self._hits.get(key)
        if hits is None:
            if not create:
                return deque()
            hits = deque()
            self._hits[key] = hits
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if not hits and not create:
            # Nothing left in the window: stop tracking it rather than keeping
            # an empty deque alive for every key ever asked about.
            self._hits.pop(key, None)
            return deque()
        self._hits.move_to_end(key)
        return hits

    def allows(self, key: str) -> bool:
        """Whether another attempt on this key is allowed right now."""
        return len(self._live(key)) < self.limit

    def record_failure(self, key: str) -> None:
        self._live(key, create=True).append(self._clock())
        self._evict()

    def _evict(self) -> None:
        while len(self._hits) > self.MAX_KEYS:
            self._hits.popitem(last=False)

    def reset(self) -> None:
        """Forget everything. For tests: the limiters are module-level, so one
        test's failed sign-ins would otherwise count against the next one's."""
        self._hits.clear()

    def clear(self, key: str) -> None:
        """Forget this key's failures — what a successful sign-in does."""
        self._hits.pop(key, None)

    def retry_after(self, key: str) -> int:
        """Whole seconds until the oldest failure falls out of the window."""
        hits = self._live(key)
        if not hits:
            return 0
        return max(1, int(self.window - (self._clock() - hits[0])) + 1)
