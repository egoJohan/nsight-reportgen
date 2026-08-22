"""Runnable nSight API server: `uvicorn reportbuilder.api.server:app` (or python -m ...).

Enables CORS so the dev frontend (localhost) can call it.

Storage is datahive, always: `NSIGHT_DATAHIVE_URL` + `NSIGHT_DATAHIVE_TOKEN`.
The former demo mode (NSIGHT_DEMO=1, a JSON store under work/demo-store) is gone
— its data is left on disk, unread.
"""
from __future__ import annotations

import os

from fastapi.middleware.cors import CORSMiddleware

from reportbuilder.api.app import create_app


def _require_datahive() -> None:
    """Refuse to start a SERVER without a hive to store anything in.

    `build_repository` falls back to an in-memory store when NSIGHT_DATAHIVE_URL
    is unset — right for tests, catastrophic for a deployment: every customer,
    case, material, report, user and grant lives until the next restart and no
    further, and nothing says so. The staging compose file shipped in exactly
    that state for months, still setting the NSIGHT_DEMO variables that stopped
    meaning anything when demo mode was removed.

    This is the runnable server's entrypoint, not `create_app`, so tests keep
    their in-memory store; only a process someone deploys is held to it.
    """
    missing = [name for name in ("NSIGHT_DATAHIVE_URL", "NSIGHT_DATAHIVE_TOKEN")
               if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "refusing to start without datahive: " + ", ".join(missing) +
            " unset. Storage is datahive, always — see this module's docstring. "
            "Without it the store is in-memory and every write is lost on restart."
        )


def build_server_app():

    # No client is injected: get_client resolves per request, carrying the
    # caller's auth, and is backed by datahive through the repository. Passing
    # one here would override that dependency for every request in the process
    # — which is exactly the bug this replaces, where the old DataHiveClient
    # silently won over the new wiring.
    app = create_app()
    origins = os.environ.get("NSIGHT_CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        # The fast chart preview reports the template's title box in response
        # headers instead of the body (the body is PNG bytes) — without this,
        # the browser drops them before JS ever sees them, and the frontend's
        # title overlay silently never appears.
        expose_headers=[
            "X-Title-Box", "X-Title-Font", "X-Title-Size-Pt", "X-Title-Color",
            "X-Title-Align", "X-Title-Caps", "X-Slide-Aspect",
        ],
    )
    return app


def __getattr__(name: str):
    """`app` is built on ACCESS, not on import, and only after the datahive check.

    uvicorn resolves "reportbuilder.api.server:app" by importing this module and
    then reading the attribute, so the guard still fires before a deployed
    process serves a single request. Importing the module — which the tests do,
    to reach `build_server_app` — touches nothing and stays free.

    Building it at import time instead would make the module unimportable
    without a hive configured, which is not the same statement at all: a factory
    that tests drive with no datahive is legitimate, a SERVER without one is not.
    """
    if name == "app":
        _require_datahive()
        return build_server_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")



def main():
    import logging
    import uvicorn

    # uvicorn configures its OWN loggers and leaves the root one bare, so
    # nothing the application logs is ever printed — including the warning that
    # says a customer's template could not be harvested, and the line that says
    # where a slow render spent its time. NSIGHT_LOG_LEVEL raises or lowers it.
    logging.basicConfig(
        level=os.environ.get("NSIGHT_LOG_LEVEL", "INFO").upper(),
        format="%(levelname)s:%(name)s: %(message)s",
    )

    # Dev hot-reload: NSIGHT_RELOAD=1 restarts the server when backend source
    # changes (watches src/reportbuilder only, so frontend edits don't churn it).
    reload = os.environ.get("NSIGHT_RELOAD") == "1"
    uvicorn.run(
        "reportbuilder.api.server:app",
        host=os.environ.get("NSIGHT_HOST", "127.0.0.1"),
        port=int(os.environ.get("NSIGHT_PORT", "8200")),
        reload=reload,
        reload_dirs=["src/reportbuilder"] if reload else None,
    )


if __name__ == "__main__":
    main()
