"""PDF page rasterization for preview + judge (design §10)."""
from __future__ import annotations
import glob
import os
import subprocess
import pdfplumber

def pdf_page_to_png(pdf_path: str, page_index: int, out_path: str, *, resolution: int = 150) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_index]
        page.to_image(resolution=resolution).save(out_path, format="PNG")
    return out_path


def rasterize_pages(pdf_path: str, out_dir: str, *, dpi: int = 150) -> list[str]:
    """All PDF pages -> one PNG each via poppler pdftoppm; return ordered PNG paths."""
    os.makedirs(out_dir, exist_ok=True)
    prefix = os.path.join(out_dir, "page")
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), pdf_path, prefix],
                   capture_output=True, check=True)
    return sorted(glob.glob(os.path.join(out_dir, "page*.png")))


def slide_view(pdf_path: str, out_dir: str, *, dpi: int = 150) -> list[str]:
    """PPT-style view: one image per slide/page (REQ-C-19b). Same artifact as page_view."""
    return rasterize_pages(pdf_path, out_dir, dpi=dpi)


def page_view(pdf_path: str, out_dir: str, *, dpi: int = 150) -> list[str]:
    """PDF-style continuous-page view (REQ-C-19a/b). Same artifact as slide_view."""
    return rasterize_pages(pdf_path, out_dir, dpi=dpi)
