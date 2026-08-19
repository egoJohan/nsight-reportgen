"""PDF page rasterization for preview + judge (design §10)."""
from __future__ import annotations
import glob
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import pdfplumber

def pdf_page_to_png(pdf_path: str, page_index: int, out_path: str, *, resolution: int = 150) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_index]
        page.to_image(resolution=resolution).save(out_path, format="PNG")
    return out_path


def _page_count(pdf_path: str) -> int:
    """Pages in *pdf_path*, or 0 when it cannot be read cheaply."""
    try:
        out = subprocess.run(["pdfinfo", pdf_path], capture_output=True,
                             check=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return 0
    for line in out.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1])
            except ValueError:
                return 0
    return 0


def rasterize_pages(pdf_path: str, out_dir: str, *, dpi: int = 150,
                    workers: int | None = None) -> list[str]:
    """All PDF pages -> one PNG each via poppler pdftoppm; return ordered PNG paths.

    One pdftoppm renders pages one after another on a single core, which on a
    60-slide deck was half a minute of a render the analyst is waiting through.
    The pages are independent, so they go out in chunks across processes.

    Safe to split: pdftoppm pads the page number by the DOCUMENT's page count,
    not the chunk's, so `page-09.png` is named that whether it was rendered
    alone or with pages 1-8, and the sort below still orders the deck.
    """
    os.makedirs(out_dir, exist_ok=True)
    prefix = os.path.join(out_dir, "page")

    def _run(first: int = 0, last: int = 0) -> None:
        cmd = ["pdftoppm", "-png", "-r", str(dpi)]
        if first and last:
            cmd += ["-f", str(first), "-l", str(last)]
        subprocess.run(cmd + [pdf_path, prefix], capture_output=True, check=True)

    pages = _page_count(pdf_path)
    n = workers or max(1, min(8, (os.cpu_count() or 2) - 2))
    if pages < 2 or n < 2:
        _run()
    else:
        n = min(n, pages)
        size = -(-pages // n)                     # ceil, so n chunks cover all
        spans = [(i + 1, min(i + size, pages)) for i in range(0, pages, size)]
        with ThreadPoolExecutor(max_workers=len(spans)) as pool:
            # Each pdftoppm is its own process, so this is real parallelism; the
            # threads only wait on them.
            for fut in [pool.submit(_run, a, b) for a, b in spans]:
                fut.result()
    return sorted(glob.glob(os.path.join(out_dir, "page*.png")))


def slide_view(pdf_path: str, out_dir: str, *, dpi: int = 150) -> list[str]:
    """PPT-style view: one image per slide/page (REQ-C-19b). Same artifact as page_view."""
    return rasterize_pages(pdf_path, out_dir, dpi=dpi)


def page_view(pdf_path: str, out_dir: str, *, dpi: int = 150) -> list[str]:
    """PDF-style continuous-page view (REQ-C-19a/b). Same artifact as slide_view."""
    return rasterize_pages(pdf_path, out_dir, dpi=dpi)
