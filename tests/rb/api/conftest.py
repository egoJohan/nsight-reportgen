"""Shared wiring for tests/rb/api.

Since `5547ab6` (route guards), every data route resolves a user via
`current_user` — which needs `get_auth` to answer — and every case/material/
customer-addressed route resolves that id through the `Repository`, not
through whatever DataHive client the route body was given. A test built with
only `create_app(client=<Mock>)` and no repository/auth overrides now fails
closed: 401 with no bearer token, or 404 for a placeholder id like "mat-1"
that exists in the mock but not in the repository the guard actually asks.

`wire()` below is the fix, and mirrors `client_mock`/`client_memory` in
tests/suite/conftest.py: seed one customer/case/material in a real
`Repository`, override `get_repository`/`get_auth` with it, and hand back
their ids so a test can address a guarded route with something the guard can
actually resolve.
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


def wire(client=None) -> TestClient:
    """A TestClient with a real, seeded Repository behind its auth/guards.

    `client` is whatever DataHive client the route body itself should see
    (a Mock, an InMemoryDataHiveClient, ...) — it need not agree with the
    repository's own ids unless a test also asserts continuity between the
    two (see tests/suite/conftest.py's client_mock for that case).
    """
    auth = AuthContext(token="test")
    repo = Repository(InMemoryObjectStore())
    customer = repo.create_customer(auth, "RB Co")
    case = repo.create_case(auth, customer.id, "RB Case")
    material = repo.attach_material(auth, customer.id, case.id, "rb.sav", b"")

    app = create_app(client=client)
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    tc = TestClient(app)
    # A route guard resolves ids through the repository, so a test addressing
    # a guarded route needs THESE ids, not an arbitrary placeholder string.
    tc.customer_id = customer.id
    tc.case_id = case.id
    tc.material_id = material.id
    return tc


@pytest.fixture
def rb_wire():
    """Factory fixture: rb_wire(client=None) -> guard-ready TestClient.

    Use this directly when a test needs more than one independently-wired
    client, or needs a client with no DataHive client injected at all
    (`create_app()`'s own default `get_client` wiring).
    """
    return wire


@pytest.fixture
def rb_mock() -> Mock:
    """A bare Mock standing in for DataHiveClient. Configure its return
    values before the request, same as before this fixture existed."""
    return Mock()


@pytest.fixture
def rb_client(rb_mock) -> TestClient:
    """The common case: one Mock DataHive client, one wired TestClient."""
    return wire(client=rb_mock)


@pytest.fixture
def rb_client_memory() -> TestClient:
    """App wired the way production is: no injected client, so `get_client`
    builds a RepositoryClient over the same repository the guards use.

    Needed wherever a test round-trips data through the client AND the guard
    — e.g. renaming a case and then listing it back — since a Mock client and
    the guard's repository would otherwise be two unrelated stores.
    """
    return wire(client=None)


@pytest.fixture
def delete_with_consent():
    """Factory: delete_with_consent(client, url) -> Response.

    The in-memory seam mirrors datahive's real behaviour (floor rule 4): the
    first delete of any object comes back 409 needing approval. Loop through
    the consent gate until the delete actually happens, same pattern as
    tests/suite/integration/api/test_cases_crud.py's `_delete_with_consent`.
    """
    def _delete(client: TestClient, url: str):
        repo = client.app.dependency_overrides[get_repository]()
        for _ in range(50):
            resp = client.delete(url)
            if resp.status_code != 409:
                return resp
            repo.store.approve(resp.json()["detail"]["request_id"])
        raise AssertionError("consent loop did not converge")
    return _delete
