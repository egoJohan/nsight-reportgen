"""GET /admin/process — what the backend process holds right now.

See api/process_health.py for why. Admin-only: /readyz stays the public "is it
up", and this is for whoever runs the box.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from reportbuilder.api import process_health
from reportbuilder.api.deps_auth import require_admin
from reportbuilder.auth.permissions import User

process_router = APIRouter(tags=["admin"])


@process_router.get("/admin/process")
def admin_process(admin: User = Depends(require_admin)) -> dict:
    del admin
    return process_health.snapshot()
