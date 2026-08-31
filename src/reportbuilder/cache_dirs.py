"""Where nSight keeps its on-disk caches — deliberately NOT the temp dir.

Every cache here used to hang off ``tempfile.gettempdir()``. On a host where
``/tmp`` is a tmpfs — the default on many distributions, including this
developer's machine and the local one-core setup — that is RAM, not disk: 61 MB
of rendered previews were sitting in memory on a 4 GB box, and rendered decks
(``nsight-render``) are whole PPTX/PDF files. ``export/cleanup.py`` already
described the problem ("in a /tmp that is a ramfs, so it was real memory") and
swept the directories periodically; sweeping is a mitigation, and the caches
belong on disk in the first place.

Resolution order, first that is set:

1. ``NSIGHT_CACHE_DIR``  — explicit, and what the containers set.
2. ``XDG_CACHE_HOME``/nsight — the platform convention.
3. ``~/.cache/nsight``  — the default.

These are caches, not data: everything under here is content-keyed and
regenerates on demand. Losing the directory costs time, never information.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def _configured_root() -> Path:
    explicit = os.environ.get("NSIGHT_CACHE_DIR")
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "nsight"
    return Path(os.path.expanduser("~")) / ".cache" / "nsight"


def cache_root() -> Path:
    """The cache root, created. Falls back to the temp dir only if the chosen
    location cannot be created — a cache that cannot be made must not take the
    server down, even though the fallback is the very place we are avoiding."""
    root = _configured_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        return root
    except OSError as e:
        fallback = Path(tempfile.gettempdir()) / "nsight-cache"
        log.warning("cache dir %s unusable (%s); falling back to %s, which may "
                    "be a ramdisk", root, e, fallback)
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _sub(name: str) -> Path:
    d = cache_root() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def preview_root() -> Path:
    """Rendered slide previews, keyed by material + spec + rendering identity."""
    return _sub("preview")


def render_root() -> Path:
    """Exported decks awaiting download. The largest things written here."""
    return _sub("render")


def ground_root() -> Path:
    """Rasterised template backgrounds ("grounds"), keyed by template + dpi."""
    return _sub("ground")


def template_root() -> Path:
    """One copy of each distinct template CONTENT a preview renders from."""
    return _sub("templates")


def scratch_root() -> Path:
    """Intermediate files: uploaded .sav and .pptx, backup/restore ZIPs, chart
    PNGs, LibreOffice's own working files. Short-lived, but not small — an
    uploaded SPSS file can be hundreds of megabytes, and in a tmpfs that is
    hundreds of megabytes of RAM."""
    return _sub("scratch")


def use_disk_backed_tempdir() -> Path:
    """Point this PROCESS's temp dir at disk, and return it.

    Fourteen places write intermediates through `tempfile` directly, and the
    module defaults to /tmp — a tmpfs on many hosts. Redirecting the default
    covers all of them at once, including code we do not own, and exporting
    TMPDIR carries it into child processes: LibreOffice writes its own
    intermediates during a PPTX->PDF conversion and only the environment
    reaches it.

    Idempotent, and safe to call before anything has used tempfile.
    """
    scratch = scratch_root()
    tempfile.tempdir = str(scratch)
    os.environ["TMPDIR"] = str(scratch)
    return scratch


def profile_root() -> Path:
    """LibreOffice user profiles. Scratch, but LibreOffice writes freely into
    them during a conversion, so they do not belong in RAM either."""
    return _sub("lo-profiles")
