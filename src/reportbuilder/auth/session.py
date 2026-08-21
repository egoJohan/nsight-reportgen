"""Sessions: minting, resolving, and revoking (spec §4, §7).

A session is two things at once: a record in datahive
(`Repository.create_session`/`get_session`/...) and a signed, opaque id
inside an HttpOnly cookie. A well-formed signature only proves the id was
ISSUED here — a live record is what `resolve` returns, and that record can
be gone (revoked, expired, its user deleted) while the signature still
checks out.

Resolution is cached in-process for CACHE_TTL_SECONDS (spec §7): "removing a
user's access must take effect without waiting for a token to expire... a
revocation takes effect within that window, and a sign-out evicts
immediately on the node that handled it." If nSight ever runs as more than
one process, this TTL becomes the revocation guarantee across the fleet.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import itsdangerous

from reportbuilder.auth.permissions import User
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

COOKIE_NAME = "nsight_session"
ABSOLUTE_LIFETIME_SECONDS = 30 * 24 * 3600   # from creation, never extended
IDLE_TIMEOUT_SECONDS = 12 * 3600             # since last_seen, extended on activity
TOUCH_MIN_INTERVAL_SECONDS = 60              # coalesce last_seen writes
CACHE_TTL_SECONDS = 30.0                     # spec §7

_SALT = "nsight-session-cookie-v1"


def _codec(signing_key: bytes) -> itsdangerous.URLSafeTimedSerializer:
    return itsdangerous.URLSafeTimedSerializer(signing_key, salt=_SALT)


def cookie_value(signing_key: bytes, session_id: str) -> str:
    return _codec(signing_key).dumps(session_id)


def session_id_from_cookie(signing_key: bytes, cookie: str) -> str | None:
    """The session id inside *cookie*, or None if it is absent, malformed,
    signed with a different key, or older than the absolute lifetime."""
    try:
        value = _codec(signing_key).loads(cookie, max_age=ABSOLUTE_LIFETIME_SECONDS)
    except itsdangerous.BadData:
        return None
    return value if isinstance(value, str) else None


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _expired(record, now: datetime) -> bool:
    if now >= _parse(record.expires):
        return True
    idle_since = (now - _parse(record.last_seen)).total_seconds()
    return idle_since > IDLE_TIMEOUT_SECONDS


_MISS = object()  # "nothing cached" — distinct from a cached negative result


class _Cache:
    """session id -> (User | None, cached_at, ttl_seconds).

    Keyed by session id, not by user id or by a permission decision: what is
    cached is a specific session's resolved identity, so one session can
    never read another session's cache entry, and no "answer" (allow/deny)
    is ever cached independently of the session that earned it.

    Two kinds of entry, two lifetimes:

    - A positive hit from `put` (a live session's User) lives for
      CACHE_TTL_SECONDS — spec §7's ordinary revocation window.
    - A tombstone from `revoke` (None) lives for ABSOLUTE_LIFETIME_SECONDS.
      This is the fix for a real gap: `Repository.delete_session` swallows
      `ConsentRequired` and returns normally even when the underlying record
      was NOT physically removed (see its docstring) — so a plain cache
      *eviction* on sign-out would just send the very next `resolve` back to
      `repo.get_session`, which can still find that same live, unexpired
      record and hand the session right back out. A tombstone instead
      stands in as the answer directly, on this node, so sign-out is
      immediate regardless of whether the delete landed. It only needs to
      outlive the record's own worst case: the record's `expires` is at
      most `created + ABSOLUTE_LIFETIME_SECONDS`, and revoke happens at or
      after `created`, so a tombstone held for ABSOLUTE_LIFETIME_SECONDS
      *from the moment of revoke* never expires before the record itself
      would — `get_session`'s own expiry check has taken over by the time
      this entry would be pruned, so forgetting it then is safe, and the
      cache does not grow without bound forever.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[User | None, float, float]] = {}

    def get(self, session_id: str):
        hit = self._entries.get(session_id)
        if hit is None:
            return _MISS
        value, cached_at, ttl = hit
        if time.monotonic() - cached_at > ttl:
            self._entries.pop(session_id, None)
            return _MISS
        return value

    def put(self, session_id: str, user: User) -> None:
        self._entries[session_id] = (user, time.monotonic(), CACHE_TTL_SECONDS)

    def revoke(self, session_id: str) -> None:
        self._entries[session_id] = (None, time.monotonic(), ABSOLUTE_LIFETIME_SECONDS)

    def forget_user(self, user_id: str) -> None:
        """Drop every live entry for one user, so their next request re-reads
        their grants instead of waiting out the TTL.

        Only positive entries: a tombstone means "this session is gone" and
        must keep standing until it expires on its own terms (see above).
        """
        for sid, (value, _, _) in list(self._entries.items()):
            if value is not None and value.id == user_id:
                self._entries.pop(sid, None)


_cache = _Cache()


def forget_user(user_id: str) -> None:
    """Invalidate this node's cached identity for *user_id*.

    For a grant change the user must see AT ONCE — the customer they just
    created appearing in their own sidebar — rather than within
    CACHE_TTL_SECONDS. Same single-process caveat as the TTL itself: with more
    than one process the TTL remains the guarantee, and this is an
    optimisation on the node that made the change.
    """
    _cache.forget_user(user_id)


def create(repo: Repository, auth: AuthContext, user_id: str) -> str:
    """Start a session for *user_id*. Returns the bare session id — the
    caller cookie-encodes it with `cookie_value`."""
    record = repo.create_session(auth, user_id, ABSOLUTE_LIFETIME_SECONDS)
    return record.id


def resolve(repo: Repository, auth: AuthContext, session_id: str) -> User | None:
    """The signed-in user for *session_id*, or None.

    A cache hit skips both the session lookup and the user lookup — see the
    module docstring for what that costs under revocation. A revoked
    session's tombstone is also a hit here (a cached None), so it returns
    without touching the store at all — see `_Cache`'s docstring.
    """
    cached = _cache.get(session_id)
    if cached is not _MISS:
        return cached

    record = repo.get_session(auth, session_id)
    if record is None:
        return None
    now = datetime.now(timezone.utc)
    if _expired(record, now):
        repo.delete_session(auth, session_id)
        return None

    user = repo.get_user(auth, record.user_id)
    if user is None:
        # The user was deleted; the session outlives them by at most one
        # resolution, cleaned up right here.
        repo.delete_session(auth, session_id)
        return None

    idle_since = (now - _parse(record.last_seen)).total_seconds()
    if idle_since > TOUCH_MIN_INTERVAL_SECONDS:
        repo.touch_session(auth, session_id, now.isoformat(timespec="seconds"))

    _cache.put(session_id, user)
    return user


def revoke(repo: Repository, auth: AuthContext, session_id: str) -> None:
    """Sign out: delete the record, and make this session resolve to None on
    this node immediately (spec §7) — not just until the next store read.

    `delete_session` swallows `ConsentRequired` and returns normally without
    the record necessarily having been physically removed (see its
    docstring): nothing here may assume the delete took effect. So instead
    of merely evicting the cache entry — which would just let the very next
    `resolve` fall through to `repo.get_session` and find that same live,
    unexpired record again — this writes a tombstone that `resolve` treats
    as an immediate cache hit for None. Correctness therefore rests on the
    session being unusable from cache, not on the delete having succeeded.
    """
    repo.delete_session(auth, session_id)
    _cache.revoke(session_id)
