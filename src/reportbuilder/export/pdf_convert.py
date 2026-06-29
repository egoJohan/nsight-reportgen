"""LibreOffice headless PPTX -> PDF conversion (design §10, R5).

FONT NOTE: soffice substitutes any font missing on the runner, shifting label
metrics and risking the R3 layout. The conversion env should pin fonts; an
isolated profile dir keeps conversion deterministic. TODO: wire OO_FONTDIR once
the style spec lands.

CONCURRENCY: a single shared LibreOffice user profile is lock-guarded, so naive
concurrent soffice calls collide. We keep a small POOL of per-slot profile dirs
(``-env:UserInstallation``); acquiring a slot bounds concurrency AND lets several
conversions run in parallel without stepping on each other. Profiles are reused
across calls so the (slow) first-run profile init happens once per slot.
"""
from __future__ import annotations
import os
import queue
import shutil
import subprocess
import tempfile
from pathlib import Path

def pdf_page_count(pdf_path: str) -> int:
    """Page count via poppler `pdfinfo`. (REQ-C-21/28a)"""
    proc = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True, check=True)
    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError("pdfinfo: no Pages line in output")


# Bound concurrent soffice processes — each is heavy (startup + memory). Sized to
# the box; conversions beyond this queue for a free profile slot.
_MAX_CONCURRENT = max(1, min(4, (os.cpu_count() or 2)))
# Namespace the profile root by PID so multiple worker PROCESSES (gunicorn/uvicorn
# --workers N) never hand out the same UserInstallation dir to two concurrent
# soffice invocations — which would re-introduce the single-instance-per-profile
# lock contention/corruption the slot pool exists to prevent.
_PROFILE_ROOT = Path(tempfile.gettempdir()) / "nsight-lo-profiles" / f"pid-{os.getpid()}"

# A queue of profile dirs acts as both the concurrency gate (get() blocks until a
# slot is free) and the per-conversion isolation (each slot has its own profile).
_profile_slots: "queue.Queue[Path]" = queue.Queue()
for _i in range(_MAX_CONCURRENT):
    _p = _PROFILE_ROOT / f"slot-{_i}"
    _p.mkdir(parents=True, exist_ok=True)
    _profile_slots.put(_p)
del _i, _p


def pptx_to_pdf(pptx_path: str, out_dir: str) -> str:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise RuntimeError("LibreOffice (soffice) not found on PATH")
    os.makedirs(out_dir, exist_ok=True)

    # Acquire an isolated profile slot — blocks (bounding concurrency) until free.
    profile = _profile_slots.get()
    try:
        proc = subprocess.run(
            [
                soffice,
                f"-env:UserInstallation=file://{profile}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                out_dir,
                pptx_path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        _profile_slots.put(profile)

    if proc.returncode != 0:
        raise RuntimeError(f"soffice failed ({proc.returncode}): {proc.stderr}")
    base = os.path.splitext(os.path.basename(pptx_path))[0]
    pdf = os.path.join(out_dir, base + ".pdf")
    if not os.path.exists(pdf):
        raise RuntimeError(f"expected PDF not produced: {pdf}\n{proc.stdout}")
    return pdf
