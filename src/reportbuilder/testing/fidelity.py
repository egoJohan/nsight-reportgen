"""Objective number gates — fidelity layers 1 & 2 (design §10)."""
from __future__ import annotations
import re
import pdfplumber
from pptx import Presentation
from reportbuilder.stats.series import SeriesResult

_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")

def numbers_from_pptx(pptx_path: str) -> dict:
    """Read native chart series values: {series_name: [float, ...]}."""
    prs = Presentation(pptx_path)
    out: dict[str, list[float]] = {}
    for slide in prs.slides:
        for shape in slide.shapes:
            if not getattr(shape, "has_chart", False):
                continue
            for plot in shape.chart.plots:
                for series in plot.series:
                    out[series.name] = [float(v) for v in series.values]
    return out

def numbers_from_pdf(pdf_path: str) -> list[float]:
    """Every numeric token in the rendered PDF text (data labels are real text)."""
    nums: list[float] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for tok in _NUM.findall(text):
                nums.append(float(tok.replace(",", ".")))
    return nums

def _expected_values(series: SeriesResult) -> list[float]:
    attr = {"pct": "pct", "count": "count", "mean": "mean"}[series.statistic]
    vals: list[float] = []
    for cat in series.categories:
        for seg in series.segments:
            v = getattr(series.cell(cat, seg), attr)
            if v is not None:
                vals.append(float(v))
    return vals

def assert_series_match(extracted: dict, series: SeriesResult, tol: float = 0.5) -> None:
    """Every SeriesResult value (per its statistic) appears in `extracted` within `tol`."""
    pool: list[float] = []
    for v in extracted.values():
        pool.extend(v if isinstance(v, (list, tuple)) else [v])
    missing = [
        exp for exp in _expected_values(series)
        if not any(abs(exp - got) <= tol for got in pool)
    ]
    assert not missing, f"values not found within tol={tol}: {missing} in {pool}"
