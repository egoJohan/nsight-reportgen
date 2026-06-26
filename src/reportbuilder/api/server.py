"""Runnable nSight API server: `uvicorn reportbuilder.api.server:app` (or python -m ...).

Builds the app with a real DataHiveClient from env, and enables CORS so the Flutter
dev app (localhost) can call it.
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
        return InMemoryDataHiveClient()
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

    uvicorn.run(
        "reportbuilder.api.server:app",
        host=os.environ.get("NSIGHT_HOST", "127.0.0.1"),
        port=int(os.environ.get("NSIGHT_PORT", "8200")),
        reload=False,
    )


if __name__ == "__main__":
    main()
