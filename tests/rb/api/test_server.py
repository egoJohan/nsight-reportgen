"""Tests for runnable server entrypoint + env DataHiveClient factory (REQ-C-30).

No real server is started; no live datahive is contacted.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.server import build_server_app
from reportbuilder.config import datahive_client_from_env
from reportbuilder.store.datahive_client import DataHiveClient


# ---------------------------------------------------------------------------
# build_server_app
# ---------------------------------------------------------------------------


def test_build_server_app_health(monkeypatch):
    """build_server_app() returns a FastAPI app; GET /health → 200 {"status":"ok"}. (REQ-C-30)"""
    # Ensure NSIGHT_DATAHIVE_URL is unset so datahive_client_from_env() returns None
    monkeypatch.delenv("NSIGHT_DATAHIVE_URL", raising=False)
    app = build_server_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    # Checked by key, not whole-body equality: /health also reports
    # `render_concurrency` (how many slides this server draws at once,
    # which the client cannot guess and sizes its queue by), and an
    # exact-match assertion makes every future field a failure here.
    body = response.json()
    assert body["status"] == "ok"
    assert body["render_concurrency"] >= 1


def test_build_server_app_cors_default(monkeypatch):
    """Default CORS (NSIGHT_CORS_ORIGINS unset → '*') adds access-control-allow-origin. (REQ-C-30)"""
    monkeypatch.delenv("NSIGHT_DATAHIVE_URL", raising=False)
    monkeypatch.delenv("NSIGHT_CORS_ORIGINS", raising=False)
    app = build_server_app()
    client = TestClient(app)
    response = client.get("/health", headers={"Origin": "http://localhost:1234"})
    assert "access-control-allow-origin" in response.headers


# ---------------------------------------------------------------------------
# datahive_client_from_env
# ---------------------------------------------------------------------------


def test_datahive_client_from_env_returns_none_when_url_unset(monkeypatch):
    """datahive_client_from_env() returns None when NSIGHT_DATAHIVE_URL is unset. (REQ-C-30)"""
    monkeypatch.delenv("NSIGHT_DATAHIVE_URL", raising=False)
    assert datahive_client_from_env() is None


def test_datahive_client_from_env_returns_client_with_correct_base_url(monkeypatch):
    """datahive_client_from_env() returns a DataHiveClient with the right base_url. (REQ-C-30)"""
    monkeypatch.setenv("NSIGHT_DATAHIVE_URL", "https://datahive.example.com")
    monkeypatch.delenv("NSIGHT_DATAHIVE_TOKEN", raising=False)
    monkeypatch.delenv("NSIGHT_DATAHIVE_TENANT", raising=False)
    monkeypatch.delenv("NSIGHT_DATAHIVE_TEMPLATE", raising=False)
    result = datahive_client_from_env()
    assert isinstance(result, DataHiveClient)
    assert result.base_url == "https://datahive.example.com"
    result.close()
