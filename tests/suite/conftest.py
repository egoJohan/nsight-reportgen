"""Shared fixtures for the fresh backend suite (`tests/suite`).

Deterministic by default: no network, no soffice. DataHive is an injected Mock
or a real InMemoryDataHiveClient; egoHive/LLM is mocked. See the plan at
docs/superpowers/plans/2026-07-01-backend-test-suite-plan.md.
"""
from __future__ import annotations

import shutil
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.store.datahive_client import DataHiveClient
from reportbuilder.store.memory_client import InMemoryDataHiveClient
from reportbuilder.testing.fixtures import synthetic_sav, synthetic_sav_bytes

from suite._helpers import RecordingChat, sign_in_override


# ---- SAV / model fixtures --------------------------------------------------

@pytest.fixture
def synthetic_bytes() -> bytes:
    return synthetic_sav_bytes()


@pytest.fixture
def synthetic_model(tmp_path):
    """(df, enriched model) from the synthetic SAV — the standard data fixture."""
    df, model = read_sav(synthetic_sav(tmp_path))
    return df, enrich_model(model)


# ---- DataHive seams --------------------------------------------------------

@pytest.fixture
def mock_hive(synthetic_bytes) -> Mock:
    """A Mock DataHiveClient whose get_material returns the synthetic SAV bytes."""
    m = Mock(spec=DataHiveClient)
    m.get_material.return_value = synthetic_bytes
    return m


@pytest.fixture
def client_mock(mock_hive) -> TestClient:
    """App on the mock store, with the repository and auth dependencies filled.

    The mock answers the data calls (attach_material, get_material, ...); the
    repository answers "does this exist and whose is it" — the split a route
    guard introduces. Seeded here with one customer, one case and one material
    so a guard resolving a case_id/material_id through the repository finds
    one, and the mock's own ids are set to agree with the seeded ones so a
    test can address either.

    The preview route now resolves a template through the object store, so
    without the repository/auth overrides it fails closed with 401 — correct
    in production, useless in a test asserting a 422 or a 503.
    """
    from reportbuilder.api.deps_store import get_auth, get_repository
    from reportbuilder.store.memory_objects import InMemoryObjectStore
    from reportbuilder.store.repository import Repository
    from reportbuilder.store.seam import AuthContext

    auth = AuthContext(token="test")
    repo = Repository(InMemoryObjectStore())
    customer = repo.create_customer(auth, "Mock Co")
    case = repo.create_case(auth, customer.id, "Mock Case")
    material = repo.attach_material(auth, customer.id, case.id, "mock.sav", b"")

    mock_hive.create_case.return_value = case.id
    mock_hive.attach_material.return_value = material.id

    app = create_app(client=mock_hive)
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(repo, auth)
    tc = TestClient(app)
    # A route guard resolves ids through the repository, so a test addressing a
    # guarded route needs THESE ids, not an arbitrary string — the mock's own
    # methods (get_material, attach_material, ...) stay id-agnostic.
    tc.customer_id = customer.id
    tc.case_id = case.id
    tc.material_id = material.id
    return tc


@pytest.fixture
def memory_hive(tmp_path) -> InMemoryDataHiveClient:
    """A real local-fs InMemoryDataHiveClient rooted at a throwaway dir."""
    store = tmp_path / "store"
    store.mkdir(parents=True, exist_ok=True)
    return InMemoryDataHiveClient(storage_dir=str(store))


@pytest.fixture
def client_memory() -> TestClient:
    """App wired the way production is: `get_client` builds a RepositoryClient
    over the same object store the repository dependency returns.

    It used to inject a separate InMemoryDataHiveClient, which meant a material
    created through a route lived in one store while anything reading the
    repository saw another. That was invisible while nothing cross-checked the
    two — and became a wall of 404s the moment route guards started resolving
    ids through the repository.
    """
    from reportbuilder.api.deps_store import get_auth, get_repository
    from reportbuilder.store.memory_objects import InMemoryObjectStore
    from reportbuilder.store.repository import Repository
    from reportbuilder.store.seam import AuthContext

    app = create_app()
    repo = Repository(InMemoryObjectStore())
    auth = AuthContext(token="test")
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(repo, auth)
    return TestClient(app)


# ---- Agentic seam ----------------------------------------------------------

@pytest.fixture
def canned_chat():
    """Factory: canned_chat(reply) -> RecordingChat. Default echoes a fixed line."""
    def _make(reply="Avainviesti: testitulos."):
        return RecordingChat(reply)
    return _make


# ---- Capability gates ------------------------------------------------------

@pytest.fixture(scope="session")
def has_soffice() -> bool:
    return bool(shutil.which("soffice") or shutil.which("libreoffice"))


@pytest.fixture
def require_soffice(has_soffice):
    if not has_soffice:
        pytest.skip("LibreOffice (soffice) not installed")


@pytest.fixture(autouse=True)
def _forget_parsed_savs():
    """Parsed SAVs are cached for the life of the process, keyed by content. Two
    tests that build the same synthetic file would otherwise share a parse, and a
    test asserting that something reads storage would quietly stop testing it."""
    from reportbuilder.api import model_loader

    model_loader._forget_parsed_savs()
    yield
