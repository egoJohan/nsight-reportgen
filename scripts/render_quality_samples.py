"""Render quality visual gate for Task A — pie/doughnut circular & fit-to-area,
bar labels never overlap / never ellipsis-cut.

Renders the real house-style product output (build_pptx -> pptx_to_pdf -> raster)
for a handful of Attendo questions and saves one full-slide PNG per case under
/tmp/taskA/ for visual review.

Run: uv run python scripts/render_quality_samples.py

Cases:
  1. pie            — var9 "Miten identifioit itsesi" (must be a perfect circle, fully inside the frame)
  2. doughnut       — var9 (same)
  3. vertical bar   — var20 (5 medium labels; must not collide, no '…')
  4. horizontal bar — var10 (long region labels; wrapped, no '…')
  5. var9 as its suggested chart type (the reported collision case)
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from reportbuilder import config
from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.export.preview import rasterize_pages
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
)
from reportbuilder.render.plugins import suggest_chart_type
from reportbuilder.stats.engine import compute

OUT_DIR = Path("/tmp/taskA")


def _spec(question_ref: str, chart_type: str) -> ChartSpec:
    return ChartSpec(
        question_ref=question_ref,
        chart_type=chart_type,
        statistic="pct",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="s1",
        elements=ElementToggles(),
    )


def _render_case(name: str, question_ref: str, chart_type: str, model, df, work: Path) -> str:
    """Build a 1-chart image-mode deck, convert to PDF, rasterize, save to /tmp/taskA/<name>.png."""
    report = Report(
        name=f"taskA-{name}",
        render_mode="image",
        template_ref="t.pptx",
        charts=(_spec(question_ref, chart_type),),
    )
    pptx = build_pptx(report, model, df, str(work / f"{name}.pptx"))
    pdf = None
    last_err = None
    for _ in range(3):   # soffice can transiently fail under rapid successive calls
        try:
            pdf = pptx_to_pdf(pptx, str(work))
            break
        except RuntimeError as e:
            last_err = e
            time.sleep(2)
    if pdf is None:
        raise last_err
    pngs = rasterize_pages(pdf, str(work / f"{name}_pages"), dpi=150)
    dest = OUT_DIR / f"{name}.png"
    shutil.copyfile(pngs[0], dest)
    return str(dest)


def main() -> None:
    if not config.ATTENDO_SAV.exists():
        raise SystemExit(f"Attendo SAV not found: {config.ATTENDO_SAV}")
    if shutil.which("soffice") is None:
        raise SystemExit("soffice not on PATH — required for PDF conversion")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    work = OUT_DIR / "_work"
    work.mkdir(exist_ok=True)

    df, model = read_sav(config.ATTENDO_SAV)

    # Determine var9's suggested chart type (case 5 — the reported collision case).
    q9 = model.question("var9")
    s9 = compute(q9, _spec("var9", "vertical_bar"), df, model)
    suggested = suggest_chart_type(q9, s9)
    print(f"var9 'Miten identifioit itsesi' suggested chart type: {suggested}")

    cases = [
        ("1_pie_var9", "var9", "pie"),
        ("2_doughnut_var9", "var9", "doughnut"),
        ("3_vertical_bar_var20", "var20", "vertical_bar"),
        ("4_horizontal_bar_var10", "var10", "horizontal_bar"),
        (f"5_var9_suggested_{suggested}", "var9", suggested),
    ]

    print("\nRendered PNGs:")
    for name, qref, ctype in cases:
        path = _render_case(name, qref, ctype, model, df, work)
        print(f"  {path}")


if __name__ == "__main__":
    main()
