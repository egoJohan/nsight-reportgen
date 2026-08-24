"""Dependencies for the path-addressed store (design §5).

nSight talks to datahive with its OWN service credential, which is read-write
across the tenant; datahive narrows nothing per user, reportbuilder/auth/
permissions.py does. See spec §5.3.

That credential is the only one used. This file used to prefer an
`Authorization` header from the caller, from before there was a login: the plan
was that the OIDC flow would start supplying it. It did not — sign-in is a
session cookie, no client sends this header, and nothing in the app, the tests
or the scripts ever did. What was left was a way for a request to choose which
hive nSight would read and write on its behalf, reachable by anyone who could
set a header, serving no caller at all.
"""
from __future__ import annotations

import os

from fastapi import HTTPException

from reportbuilder.store.datahive_objects import DataHiveObjectStore
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

_repository: Repository | None = None


def get_auth() -> AuthContext:
    """The app's own storage credential. Never the caller's — see the module
    docstring: who the caller is, and what they may touch, is decided by
    `current_user` and `auth/permissions.py`, not by which hive they can name."""
    token = os.environ.get("NSIGHT_DATAHIVE_TOKEN")
    if not token:
        # Fail closed and say why. Booting without it used to mean an in-memory
        # store that lost everything on restart, silently.
        raise HTTPException(401, "NSIGHT_DATAHIVE_TOKEN is unset")
    return AuthContext(token=token)


def service_auth() -> AuthContext | None:
    """The app's own identity, for work with no request behind it.

    Only the dev/service token: startup tasks have no caller whose rights they
    could borrow. None when unset, so callers skip rather than guess.
    """
    token = os.environ.get("NSIGHT_DATAHIVE_TOKEN")
    return AuthContext(token=token) if token else None


def build_repository() -> Repository:
    """Datahive when configured, otherwise in-memory so the app still runs."""
    url = os.environ.get("NSIGHT_DATAHIVE_URL")
    store = DataHiveObjectStore(url) if url else InMemoryObjectStore()
    return Repository(store)


def get_repository() -> Repository:
    """Overridden per-app in tests via `app.dependency_overrides`."""
    global _repository
    if _repository is None:
        _repository = build_repository()
    return _repository
