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

from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

_SETTINGS_KEY = "security.json"


def get_or_create_signing_key(repo: Repository, auth: AuthContext) -> bytes:
    """32 random bytes, created once and reused forever after.

    Not safe under two processes racing on a still-empty hive — each could
    generate and write its own key, and whichever wrote last wins, silently
    invalidating cookies the other already issued. Acceptable at the scale
    spec §7 already assumes (a single nSight process on a 1-CPU hive); if
    that assumption stops holding this needs a compare-and-swap the object
    seam does not currently offer.
    """
    stored = repo.get_setting(auth, _SETTINGS_KEY)
    if stored and stored.get("signing_key"):
        return base64.b64decode(stored["signing_key"])
    key = secrets.token_bytes(32)
    repo.set_setting(auth, _SETTINGS_KEY, {"signing_key": base64.b64encode(key).decode("ascii")})
    return key
