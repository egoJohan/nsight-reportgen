"""FastAPI app skeleton + dependency injection seam for report builder API."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from reportbuilder.api.deps import get_client
from reportbuilder.api.routes_ai import ai_router
from reportbuilder.api.routes_cases import cases_router
from reportbuilder.api.routes_materials import materials_router
from reportbuilder.api.routes_questions import questions_router
from reportbuilder.api.routes_render import render_router
from reportbuilder.api.routes_reports import reports_router
from reportbuilder.store.datahive_client import DataHiveClient, DataHiveError


def create_app(client: DataHiveClient | None = None) -> FastAPI:
    """Build the FastAPI app. If `client` is given (a DataHiveClient or a mock), it becomes the
    instance returned by the get_client dependency — this is how tests inject a mock without a
    live datahive. If None, get_client falls back to constructing a real DataHiveClient.
    Registers GET /health -> {"status": "ok"}. Later tasks add routers via app.include_router."""

    app = FastAPI()

    # Map DataHive errors to meaningful HTTP responses (REQ-C-30):
    # propagate client-error statuses so the UI can react (auth/not-found/bad-request);
    # collapse datahive 5xx / unexpected to 502 (bad upstream).
    @app.exception_handler(DataHiveError)
    async def _dh_err(request, exc: DataHiveError) -> JSONResponse:
        _client_statuses = (400, 401, 403, 404, 409, 422)
        status = exc.status_code if exc.status_code in _client_statuses else 502
        return JSONResponse(
            status_code=status,
            content={"detail": f"datahive: {exc.body}"[:500]},
        )

    # Register the health check endpoint
    @app.get("/health")
    def health() -> dict:
        """Health check endpoint."""
        return {"status": "ok"}

    # Include routers
    app.include_router(cases_router)
    app.include_router(materials_router)
    app.include_router(questions_router)
    app.include_router(reports_router)
    app.include_router(render_router)
    app.include_router(ai_router)

    # Inject the client if provided
    if client is not None:
        app.dependency_overrides[get_client] = lambda: client

    return app
