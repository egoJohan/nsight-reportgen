"""Evicting the temp caches nSight leaves behind.

Everything under these roots is derived and re-creatable: the deck itself lives
in datahive (see routes_render._persist_deck), the preview PDF and page rasters
come from the deck, and a LibreOffice profile is scratch space for one process.
So eviction is safe by construction — the worst case is one slower request.

Without this they only grow. On the machine this was written on: 62 LibreOffice
profile directories, every one belonging to a dead process, and 36 MB of
per-chart preview images.

Two rules the code sticks to:

* **Only our own directories.** Nothing outside the nsight-* roots is touched.
  A generic sweep of /tmp cannot tell our leftovers from another program's, and
  deleting someone else's temp file is not a mistake worth risking to reclaim a
  few megabytes.
* **Never fail the caller.** A janitor that stops the app from starting is worse
  than a full disk. Every error is logged and swallowed.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import logging

log = logging.getLogger(__name__)

TMP = Path(tempfile.gettempdir())
RENDER_ROOT = TMP / "nsight-render"
PREVIEW_ROOT = TMP / "nsight-preview"
PROFILE_ROOT = TMP / "nsight-lo-profiles"
#: The copy of each distinct template CONTENT a preview renders from, and the
#: blank slide LibreOffice draws once per template. Both are content-keyed
#: caches — deleting one costs the next request a rebuild and nothing else —
#: and neither was ever swept. On this developer's machine they had reached
#: 16 MB and counting, in a /tmp that is a ramfs, so it was real memory. A new
#: entry appears for every template anyone has ever previewed with, and nothing
#: took any of them away again.
TEMPLATE_ROOT = TMP / "nsight-preview-templates"
GROUND_ROOT = TMP / "nsight-preview-ground"

# A day is long enough that an analyst returning after lunch still gets an
# instant preview, and short enough that a week of use cannot fill a disk.
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60


@dataclass
class SweepResult:
    render: int = 0
    preview: int = 0
    profiles: int = 0
    templates: int = 0
    grounds: int = 0

    @property
    def total(self) -> int:
        return (self.render + self.preview + self.profiles
                + self.templates + self.grounds)

    def __str__(self) -> str:
        return (f"{self.render} render dir(s), {self.preview} preview dir(s), "
                f"{self.profiles} orphaned LibreOffice profile(s), "
                f"{self.templates} template copies, {self.grounds} blank slides")


def _remove(path: Path) -> bool:
    try:
        shutil.rmtree(path) if path.is_dir() else path.unlink()
        return True
    except OSError as exc:
        log.warning("cleanup: could not remove %s (%s)", path, exc)
        return False


def _age_seconds(path: Path, now: float) -> float:
    """Age by mtime. A cache entry rewritten recently is in active use, and a
    re-render rewrites its directory, so mtime tracks usefulness closely enough."""
    try:
        return now - path.stat().st_mtime
    except OSError:
        return 0.0


def sweep_stale(root: Path, max_age_seconds: float, *, depth: int = 1) -> int:
    """Remove entries under *root* older than *max_age_seconds*.

    `depth=2` for the render cache, whose entries are <case>/<report> — sweeping
    at depth 1 would drop a whole case because one of its reports went cold.
    """
    if not root.is_dir():
        return 0
    now = time.time()
    removed = 0
    try:
        candidates = list(root.iterdir()) if depth == 1 else [
            child for parent in root.iterdir() if parent.is_dir()
            for child in parent.iterdir()
        ]
    except OSError as exc:
        log.warning("cleanup: could not list %s (%s)", root, exc)
        return 0

    for entry in candidates:
        if _age_seconds(entry, now) > max_age_seconds and _remove(entry):
            removed += 1

    # A case directory emptied by the sweep above is litter of its own.
    if depth == 2:
        for parent in list(root.iterdir()):
            try:
                if parent.is_dir() and not any(parent.iterdir()):
                    _remove(parent)
            except OSError:
                pass
    return removed


def sweep_orphaned_profiles() -> int:
    """Remove LibreOffice profile dirs whose owning process is gone.

    Keyed on the pid in the directory name, so this is precise rather than
    age-based: a long render legitimately holds a profile for minutes.

    A recycled pid makes a dead process look alive, which keeps a profile that
    could have gone. That is the harmless direction; the reverse — deleting a
    profile out from under a running soffice — would break a live render.
    """
    if not PROFILE_ROOT.is_dir():
        return 0
    removed = 0
    for entry in PROFILE_ROOT.iterdir():
        if not entry.is_dir() or not entry.name.startswith("pid-"):
            continue
        try:
            pid = int(entry.name.removeprefix("pid-"))
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            if _remove(entry):
                removed += 1
        except PermissionError:
            # Alive, owned by someone else. Leave it.
            continue
    return removed


def sweep_all(max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS) -> SweepResult:
    """Evict every nSight temp cache. Never raises."""
    result = SweepResult()
    try:
        result.render = sweep_stale(RENDER_ROOT, max_age_seconds, depth=2)
        result.preview = sweep_stale(PREVIEW_ROOT, max_age_seconds, depth=1)
        result.profiles = sweep_orphaned_profiles()
        result.templates = sweep_stale(TEMPLATE_ROOT, max_age_seconds, depth=1)
        result.grounds = sweep_stale(GROUND_ROOT, max_age_seconds, depth=1)
    except Exception:  # noqa: BLE001 — see module docstring
        log.warning("cleanup: sweep failed", exc_info=True)
    if result.total:
        log.info("cleanup: removed %s", result)
    return result
