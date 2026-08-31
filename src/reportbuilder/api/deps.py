"""Dependency injection for the FastAPI app.

`get_client` used to hand out a DataHiveClient (or the JSON-file store in demo
mode). It now hands out a RepositoryClient: the same method surface, backed by
the path-addressed object store in datahive.

That one substitution moves every material- and case-keyed route — questions,
variables, preview, render, AI, chat — onto datahive without editing them, and
stops the legacy JSON store being read at all. Nothing is deleted from it; it
simply goes unreferenced.

The client is REQUEST-scoped because it carries the caller's auth. datahive
decides what that user may read, so a client shared between requests would hand
one user another's rights.
"""
from fastapi import Depends, Request

from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import User
from reportbuilder.store.repository import Repository
from reportbuilder.store.repository_client import RepositoryClient
from reportbuilder.store.seam import AuthContext


def request_scope(request, name: str) -> dict:
    """A dict that lives exactly as long as one request, shared by name.

    Several dependencies of the same request resolve the same things — the auth
    guard checks the case, then the storage client resolves it again to do the
    work — and each lookup is a serialised round-trip to a hive that handles one
    request at a time. Sharing one scope makes the second lookup free.

    It must NOT outlive the request: a case whose access changed between two
    requests has to be seen afresh. A caller with no request (an internal task,
    a test) simply gets a throwaway dict and no sharing.
    """
    state = getattr(request, "state", None)
    if state is None:
        return {}
    scopes = getattr(state, "_nsight_scopes", None)
    if scopes is None:
        scopes = {}
        state._nsight_scopes = scopes
    return scopes.setdefault(name, {})


def get_client(
    request: Request,
    auth: AuthContext = Depends(get_auth),
    repo: Repository = Depends(get_repository),
    user: User = Depends(current_user),
) -> RepositoryClient:
    """The storage client for this request, scoped to this caller.

    Shares the request's resolution scopes with the auth guard, which has
    usually resolved the same case moments earlier.
    """
    return RepositoryClient(repo, auth, user,
                            case_memo=request_scope(request, "case"),
                            material_memo=request_scope(request, "material"))
