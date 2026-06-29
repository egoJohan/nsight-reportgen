"""Runnable nSight API server: `uvicorn reportbuilder.api.server:app` (or python -m ...).

Builds the app with a real DataHiveClient from env, and enables CORS so the Flutter
dev app (localhost) can call it.

Demo mode (NSIGHT_DEMO=1) uses a self-contained store that now persists to disk so
created cases, uploaded materials, and reports survive server restarts. The on-disk
location is `NSIGHT_DEMO_DIR` (env var) when set, otherwise `<repo>/work/demo-store`
(work/ is gitignored). The directory is created if missing.
"""
from __future__ import annotations

import os

from fastapi.middleware.cors import CORSMiddleware

from reportbuilder.api.app import create_app
from reportbuilder.config import datahive_client_from_env


def _select_client():
    """Demo mode (NSIGHT_DEMO=1) uses a self-contained in-memory store so the whole
    flow runs with no datahive/token; otherwise build a real DataHiveClient from env."""
    if os.environ.get("NSIGHT_DEMO") == "1":
        from reportbuilder.store.memory_client import InMemoryDataHiveClient
        # repo root = .../proto (api -> reportbuilder -> src -> proto)
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        default_dir = os.path.join(repo_root, "work", "demo-store")
        storage_dir = os.environ.get("NSIGHT_DEMO_DIR", default_dir)
        os.makedirs(storage_dir, exist_ok=True)
        return InMemoryDataHiveClient(storage_dir=storage_dir)
    return datahive_client_from_env()  # None -> default real client (will fail until configured)


def build_server_app():
    app = create_app(client=_select_client())
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
