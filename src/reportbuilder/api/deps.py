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
from fastapi import Depends

from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.store.repository import Repository
from reportbuilder.store.repository_client import RepositoryClient
from reportbuilder.store.seam import AuthContext


def get_client(
    auth: AuthContext = Depends(get_auth),
    repo: Repository = Depends(get_repository),
) -> RepositoryClient:
    """The storage client for this request, scoped to this caller."""
    return RepositoryClient(repo, auth)
