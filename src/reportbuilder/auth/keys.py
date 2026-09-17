"""The server's own signing key (spec §9).

Lives in datahive, not an environment variable: attaching a different hive
must bring the sign-in configuration with it, and a key that regenerated on
every deploy would silently sign every existing session and OIDC-state
cookie out from under its owner. `NSIGHT_BOOTSTRAP_ADMINS` is the one
documented exception to "config lives in the store" (spec §3.1) — this is
not another one, because unlike the bootstrap list, this has somewhere to
live from the very first request.
"""
from __future__ import annotations

import base64
import secrets
import threading
import weakref

from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

_SETTINGS_KEY = "security.json"

#: The key as read, per repository (i.e. per attached hive). It never changes
#: once created, and every signed-in request asks for it: reading it from the
#: hive each time was a round trip per request for a constant, queued in front
#: of the requests doing real work on a hive that serves one at a time.
#: Weakly keyed, so a repository that goes away takes its entry with it.
#: The one thing that replaces it — a backup restore — calls
#: `forget_signing_key`. (2026-09-17)
_known: "weakref.WeakKeyDictionary[Repository, bytes]" = weakref.WeakKeyDictionary()
_lock = threading.Lock()


def forget_signing_key() -> None:
    """Read the key from the store again on next use. For a restore, which
    writes a different one underneath this process."""
    with _lock:
        _known.clear()


def get_or_create_signing_key(repo: Repository, auth: AuthContext) -> bytes:
    """32 random bytes, created once and reused forever after.

    Not safe under two processes racing on a still-empty hive — each could
    generate and write its own key, and whichever wrote last wins, silently
    invalidating cookies the other already issued. Acceptable at the scale
    spec §7 already assumes (a single nSight process on a 1-CPU hive); if
    that assumption stops holding this needs a compare-and-swap the object
    seam does not currently offer.
    """
    with _lock:
        known = _known.get(repo)
    if known is not None:
        return known
    stored = repo.get_setting(auth, _SETTINGS_KEY)
    if stored and stored.get("signing_key"):
        key = base64.b64decode(stored["signing_key"])
    else:
        key = secrets.token_bytes(32)
        repo.set_setting(auth, _SETTINGS_KEY,
                         {"signing_key": base64.b64encode(key).decode("ascii")})
    with _lock:
        _known[repo] = key
    return key
