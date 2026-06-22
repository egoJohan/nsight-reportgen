"""LibreOffice headless PPTX -> PDF conversion (design §10, R5).

FONT NOTE: soffice substitutes any font missing on the runner, shifting label
metrics and risking the R3 layout. The conversion env should pin fonts; an
isolated profile dir keeps conversion deterministic. TODO: wire OO_FONTDIR once
the style spec lands.
"""
from __future__ import annotations
import os
import shutil
import subprocess

def pptx_to_pdf(pptx_path: str, out_dir: str) -> str:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise RuntimeError("LibreOffice (soffice) not found on PATH")
    os.makedirs(out_dir, exist_ok=True)
    proc = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, pptx_path],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"soffice failed ({proc.returncode}): {proc.stderr}")
    base = os.path.splitext(os.path.basename(pptx_path))[0]
    pdf = os.path.join(out_dir, base + ".pdf")
    if not os.path.exists(pdf):
        raise RuntimeError(f"expected PDF not produced: {pdf}\n{proc.stdout}")
    return pdf
