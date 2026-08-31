"""Tests for FastAPI app skeleton + dependency injection (REQ-C-30)."""
from unittest.mock import Mock

from fastapi import Depends
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps import get_client


def test_get_health() -> None:
    """GET /health returns 200, {"status": "ok"} plus the render
    capacity the client sizes its preview queue by. (REQ-C-30)"""
    app = create_app()
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
    """create_app() with no client still builds and serves /health. (REQ-C-30)

    The body also carries `render_concurrency` — how many slides this server
    will draw at once, which the client cannot guess and needs in order to size
    its own queue. Asserted by key rather than by whole-body equality: the
    subject here is that the app builds and answers without an upstream, and an
    exact-match assertion turns any future field into a failure of THIS test.
    """
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["render_concurrency"] >= 1
