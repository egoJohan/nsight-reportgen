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
from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.store.datahive_client import DataHiveClient
from reportbuilder.store.memory_client import InMemoryDataHiveClient
from reportbuilder.testing.fixtures import synthetic_sav, synthetic_sav_bytes

from suite._helpers import RecordingChat


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
    return TestClient(create_app(client=mock_hive))


@pytest.fixture
def memory_hive(tmp_path) -> InMemoryDataHiveClient:
    """A real local-fs InMemoryDataHiveClient rooted at a throwaway dir."""
    store = tmp_path / "store"
    store.mkdir(parents=True, exist_ok=True)
    return InMemoryDataHiveClient(storage_dir=str(store))


@pytest.fixture
def client_memory(memory_hive) -> TestClient:
    return TestClient(create_app(client=memory_hive))


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
