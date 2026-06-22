"""FastAPI app skeleton + dependency injection seam for report builder API."""
from fastapi import FastAPI

from reportbuilder.api.deps import get_client
from reportbuilder.api.routes_cases import cases_router
from reportbuilder.store.datahive_client import DataHiveClient


def create_app(client: DataHiveClient | None = None) -> FastAPI:
    """Build the FastAPI app. If `client` is given (a DataHiveClient or a mock), it becomes the
    instance returned by the get_client dependency — this is how tests inject a mock without a
    live datahive. If None, get_client falls back to constructing a real DataHiveClient.
    Registers GET /health -> {"status": "ok"}. Later tasks add routers via app.include_router."""

    app = FastAPI()

    # Register the health check endpoint
    @app.get("/health")
    def health() -> dict:
        """Health check endpoint."""
        return {"status": "ok"}

    # Include routers
    app.include_router(cases_router)

    # Inject the client if provided
    if client is not None:
        app.dependency_overrides[get_client] = lambda: client

    return app
