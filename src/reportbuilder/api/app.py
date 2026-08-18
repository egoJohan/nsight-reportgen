"""FastAPI app skeleton + dependency injection seam for report builder API."""
import asyncio
import contextlib
import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from reportbuilder.api.deps import get_client
from reportbuilder.api.routes_ai import ai_router
from reportbuilder.api.routes_cases import cases_router
from reportbuilder.api.routes_customers import customers_router
from reportbuilder.api.routes_templates import templates_router
from reportbuilder.api.routes_materials import materials_router
from reportbuilder.api.routes_questions import questions_router
from reportbuilder.api.routes_render import render_router
from reportbuilder.api.routes_reports import reports_router
from reportbuilder.export.cleanup import sweep_all
from reportbuilder.store.datahive_client import DataHiveError

log = logging.getLogger(__name__)

# Sweep on boot and then daily. Boot matters most: a container that
# restarts often would otherwise never reclaim the profiles left by the
# processes it replaced.
_SWEEP_INTERVAL_SECONDS = 24 * 60 * 60


def create_app(client=None) -> FastAPI:
    """Build the FastAPI app. If `client` is given (a DataHiveClient or a mock), it becomes the
    instance returned by the get_client dependency — this is how tests inject a mock without a
    live datahive. If None, get_client falls back to constructing a real DataHiveClient.
    Registers GET /health -> {"status": "ok"}. Later tasks add routers via app.include_router."""

    async def _janitor() -> None:
        """Evict stale temp caches on boot, then once a day."""
        while True:
            # Off the event loop: the sweep walks directories and unlinks files,
            # which would otherwise stall every request while it runs.
            await asyncio.to_thread(sweep_all)
            await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)

    @contextlib.asynccontextmanager
    async def _lifespan(_app: FastAPI):
        task = None
        # Opt out for tests and one-shot scripts, where a background task that
        # deletes files is noise at best.
        if os.environ.get("NSIGHT_DISABLE_CLEANUP") != "1":
            task = asyncio.create_task(_janitor())
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(lifespan=_lifespan)

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
    app.include_router(customers_router)
    app.include_router(templates_router)
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
