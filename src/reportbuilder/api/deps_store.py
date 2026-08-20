"""Dependencies for the path-addressed store (design §5).

Auth is per-request and comes from the caller's own `Authorization` header,
because nSight talks to datahive with its own service credential, which is
read-write across the tenant. datahive no longer narrows anything per user;
reportbuilder/auth/permissions.py does. See spec §5.3.

Until login exists there is a dev fallback to `NSIGHT_DATAHIVE_TOKEN`. It is a
fallback, not a design: the routes are already shaped so that when the OIDC flow
lands, the header simply starts arriving and nothing above this file changes.
"""
from __future__ import annotations

import os

from fastapi import Header, HTTPException

from reportbuilder.store.datahive_objects import DataHiveObjectStore
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

_repository: Repository | None = None


def get_auth(authorization: str | None = Header(default=None)) -> AuthContext:
    """The caller's bearer, or the dev token when running without login."""
    if authorization and authorization.lower().startswith("bearer "):
        return AuthContext(token=authorization.split(" ", 1)[1].strip())
    token = os.environ.get("NSIGHT_DATAHIVE_TOKEN")
    if not token:
        # Fail closed and say why: an unauthenticated request must never quietly
        # fall through to somebody else's data.
        raise HTTPException(401, "No bearer token, and NSIGHT_DATAHIVE_TOKEN is unset")
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
