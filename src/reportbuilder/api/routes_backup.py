# src/reportbuilder/api/routes_backup.py
"""Backup and restore, from Settings > Backup. Admin only, both of them.

Downloading a backup hands the caller every password hash and the session
signing key in one file; restoring one rewrites the whole store. Neither is a
data operation on one customer, so neither is gated by grants — this is the
same right as managing users.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from reportbuilder.api.deps_auth import require_admin
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth import session
from reportbuilder.auth.permissions import User
from reportbuilder.store import backup
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

backup_router = APIRouter(tags=["backup"])

# A backup is streamed to a temp file rather than built in memory: the SAVs
# alone can be hundreds of megabytes, and holding the whole archive in RAM to
# hand it to the browser is the one part of this that does not scale.
_CHUNK = 1024 * 1024


def _filename() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"nsight-backup-{stamp}.zip"


@backup_router.get("/admin/backup")
def create_backup(auth: AuthContext = Depends(get_auth),
                  repo: Repository = Depends(get_repository),
                  admin: User = Depends(require_admin)):
    """The whole store as one zip, minus rendered decks and sessions."""
    fd, tmp = tempfile.mkstemp(prefix="nsight-backup-", suffix=".zip")
    os.close(fd)
    try:
        with open(tmp, "wb") as fh:
            backup.write(repo, auth, fh)
    except Exception:
        os.unlink(tmp)
        raise
    # The response owns the file from here: FileResponse streams it, then the
    # background task removes it whether the download finished or not.
    return FileResponse(
        tmp, media_type="application/zip", filename=_filename(),
        background=BackgroundTask(lambda: os.path.exists(tmp) and os.unlink(tmp)),
    )


@backup_router.post("/admin/restore")
async def restore_backup(file: UploadFile = File(...),
                         auth: AuthContext = Depends(get_auth),
                         repo: Repository = Depends(get_repository),
                         admin: User = Depends(require_admin)) -> dict:
    """Write a backup's objects back into the store.

    Overwrite in place: every object in the backup replaces whatever is at
    that path, and anything not in the backup is left where it is. So this
    restores what was lost without deleting what survived — and a customer
    deleted after the backup was taken will come back.

    The upload goes to a temp file first. Reading a zip needs seeking, and
    holding an uploaded archive in memory to get it is how a large restore
    runs the host out of RAM.
    """
    fd, tmp = tempfile.mkstemp(prefix="nsight-restore-", suffix=".zip")
    os.close(fd)
    try:
        with open(tmp, "wb") as fh:
            while chunk := await file.read(_CHUNK):
                fh.write(chunk)
        try:
            summary = backup.read(repo, auth, tmp)
        except backup.BadBackup as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — a corrupt zip is a 400, not a 500
            raise HTTPException(400, f"Could not read that file as a backup: {exc}") from exc
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    # Users, grants and the signing key have all just been replaced. Every
    # cached identity now describes a store that no longer exists.
    session.forget_all()
    return {
        "restored": summary.restored,
        "total_bytes": summary.total_bytes,
        "problems": summary.problems,
    }
