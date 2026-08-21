"""FastAPI app skeleton + dependency injection seam for report builder API."""
import asyncio
import contextlib
import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from reportbuilder.api.deps import get_client
from reportbuilder.api.routes_access_requests import access_requests_router
from reportbuilder.api.routes_backup import backup_router
from reportbuilder.api.routes_ai import ai_router
from reportbuilder.api.routes_auth import auth_router
from reportbuilder.api.routes_cases import cases_router
from reportbuilder.api.routes_customers import customers_router
from reportbuilder.api.routes_settings import settings_router
from reportbuilder.api.routes_templates import templates_router
from reportbuilder.api.routes_materials import materials_router
from reportbuilder.api.routes_questions import questions_router
from reportbuilder.api.routes_render import render_router
from reportbuilder.api.routes_reports import reports_router
from reportbuilder.api.routes_users import users_router
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

    def _sync_fonts() -> None:
        """Put datahive's stored fonts onto this host before anything renders.

        A render host starts with an empty font directory. Without this, fonts
        an admin installed weeks ago are missing until someone re-uploads them,
        and every deck silently substitutes in the meantime.

        Failure is logged, never fatal: the app must start even when datahive
        is briefly unreachable, and a missing font degrades a deck rather than
        breaking it.
        """
        import logging

        from reportbuilder.api.deps_store import get_repository, service_auth
        from reportbuilder.api.routes_settings import sync_fonts_to_host

        try:
            auth = service_auth()
            if auth is None:
                return
            results = sync_fonts_to_host(get_repository(), auth)
            ok = sum(1 for r in results if getattr(r, "ok", False))
            if results:
                logging.getLogger(__name__).info(
                    "fonts: %d/%d installed on this host", ok, len(results))
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "fonts: could not sync from datahive", exc_info=True)

    def _seed_default_template() -> None:
        """Install the house-style template if the hive has none.

        Templates resolve report -> tutkimus -> asiakas -> this one, and until
        it exists that chain ends in None: a report with no template chosen
        rendered into a blank deck, not the plain white default that was
        written for exactly that case. Building it is deterministic and
        `ensure_default_template` writes only when it is absent, so this is a
        no-op on every boot after the first — including when someone has
        replaced the default deliberately.

        Failure is logged, never fatal: same posture as the font sync. A
        missing default costs a deck its styling, not the app its start.
        """
        import logging
        import os as _os
        import tempfile

        from reportbuilder.api.deps_store import get_repository, service_auth
        from reportbuilder.render.default_template import build_default_template

        try:
            auth = service_auth()
            if auth is None:
                return
            fd, tmp = tempfile.mkstemp(prefix="nsight-default-", suffix=".pptx")
            _os.close(fd)
            try:
                build_default_template(tmp)
                with open(tmp, "rb") as fh:
                    get_repository().ensure_default_template(
                        auth, fh.read(),
                        # Set this once after changing the builder: a hive that
                        # has already been started holds a deck built by the
                        # old code, and "seed if absent" would never replace it.
                        replace=_os.environ.get("NSIGHT_RESEED_DEFAULT_TEMPLATE") == "1")
            finally:
                _os.unlink(tmp)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "default template: could not seed", exc_info=True)

    @contextlib.asynccontextmanager
    async def _lifespan(_app: FastAPI):
        task = None
        if os.environ.get("NSIGHT_DISABLE_CLEANUP") != "1":
            # Same opt-out as the janitor: tests should not shell out to
            # fc-cache or reach for datahive on import.
            await asyncio.to_thread(_sync_fonts)
            await asyncio.to_thread(_seed_default_template)
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
    app.include_router(auth_router)
    app.include_router(customers_router)
    app.include_router(templates_router)
    app.include_router(settings_router)
    app.include_router(cases_router)
    app.include_router(materials_router)
    app.include_router(questions_router)
    app.include_router(reports_router)
    app.include_router(render_router)
    app.include_router(ai_router)
    app.include_router(users_router)
    app.include_router(access_requests_router)
    app.include_router(backup_router)

    # Inject the client if provided
    if client is not None:
        app.dependency_overrides[get_client] = lambda: client

    return app
