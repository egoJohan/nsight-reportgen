"""Tests for FastAPI app skeleton + dependency injection (REQ-C-30)."""
from unittest.mock import Mock

from fastapi import Depends
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps import get_client


def test_get_health() -> None:
    """GET /health returns 200 and JSON {"status": "ok"}. (REQ-C-30)"""
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_injected_mock_is_reachable_through_dependency() -> None:
    """Injected mock client is reachable through the dependency. (REQ-C-30)"""
    the_mock = Mock()
    app = create_app(client=the_mock)

    # Register a throwaway route that depends on get_client
    captured_client = None

    @app.get("/test-injection")
    def test_injection_route(client=Depends(get_client)) -> dict:
        nonlocal captured_client
        captured_client = client
        return {"is_mock": client is the_mock}

    test_client = TestClient(app)
    response = test_client.get("/test-injection")

    assert response.status_code == 200
    assert response.json() == {"is_mock": True}
    assert captured_client is the_mock


def test_create_app_with_no_client_builds_and_serves_health() -> None:
    """create_app() with no client still builds and serves /health. (REQ-C-30)"""
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
