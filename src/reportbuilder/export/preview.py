"""PDF page rasterization for preview + judge (design §10)."""
from __future__ import annotations
import pdfplumber

def pdf_page_to_png(pdf_path: str, page_index: int, out_path: str, *, resolution: int = 150) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_index]
        page.to_image(resolution=resolution).save(out_path, format="PNG")
    return out_path
