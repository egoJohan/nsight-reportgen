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
    )
    return app


app = build_server_app()


def main():
    import uvicorn

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
