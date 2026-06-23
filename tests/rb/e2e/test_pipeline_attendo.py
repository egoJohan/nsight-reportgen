"""Attendo golden-data E2E: aided-awareness result through render → PDF.

Pushes the R1-validated Attendo aided-awareness numbers through the full
render → PPTX → PDF chain and asserts they survive into the PDF text layer
(native mode) or that a 1-page PDF is produced (image mode).

Requirements covered: REQ-C-14, REQ-C-18, REQ-C-22, REQ-C-29b.
"""
from __future__ import annotations

import os
import shutil

import pytest

from reportbuilder import config
from reportbuilder.export.pdf_convert import pdf_page_count, pptx_to_pdf
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
)
from reportbuilder.testing.fidelity import numbers_from_pdf
from reportbuilder.testing.fixtures import DECK_AIDED_AWARENESS, aided_question

# ---------------------------------------------------------------------------
# Skip guards
# ---------------------------------------------------------------------------

_NO_SAV = not config.ATTENDO_SAV.exists()
_NO_SOFFICE = shutil.which("soffice") is None
_NO_API_KEY = not os.environ.get("ANTHROPIC_API_KEY")


# ---------------------------------------------------------------------------
# Test 1 — Attendo aided-awareness through the full pipeline (REQ-C-14/18/22)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("mode", ["native", "image"])
def test_attendo_aided_awareness_through_pipeline(mode, tmp_path):
    """Push the R1-validated Attendo aided-awareness golden result through render → PDF.

    Native mode: asserts that every DECK_AIDED_AWARENESS percentage appears in
    the PDF text layer within ±1 pp (proves the R1-correct numbers survive rendering).
    Image mode: asserts only that a 1-page PDF is produced (image PNGs have no text
    layer, so number extraction is not possible).

    REQ-C-14: classifying_var=None (Total segment); the result uses the "aided" multi
    group which groups all brand checkbox variables.
    REQ-C-18: completed deck contains the requested chart (1 slide produced).
    REQ-C-22: rendered data values match engine-computed / deck-verified series within
    tolerance.
    """
    if _NO_SAV:
        pytest.skip("Attendo .sav not present")
    if _NO_SOFFICE:
        pytest.skip("soffice not on PATH — PDF conversion skipped")

    # --- Ingest ---
    df, model = read_sav(config.ATTENDO_SAV)
    model2, q = aided_question(model)
    # aided_question returns model2 with variables but no questions; add the question
    # so build_pptx can resolve it via model.question("aided").
    model2.questions.append(q)

    # --- Chart spec (mirrors golden test) ---
    spec = ChartSpec(
        question_ref="aided",
        chart_type="horizontal_bar",
        statistic="pct",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="s1",
        elements=ElementToggles(),
    )

    # --- Build 1-chart report ---
    report = Report(
        name="attendo-aided-e2e",
        render_mode=mode,
        template_ref="t.pptx",
        charts=(spec,),
    )

    # --- Build PPTX ---
    pptx = build_pptx(report, model2, df, str(tmp_path / "deck.pptx"))
    assert os.path.isfile(pptx), f"build_pptx did not produce a file: {pptx}"

    # --- Convert to PDF ---
    pdf = pptx_to_pdf(pptx, str(tmp_path))
    assert os.path.isfile(pdf), f"pptx_to_pdf did not produce a file: {pdf}"

    # --- Page count == 1 chart (REQ-C-18, REQ-C-21) ---
    assert pdf_page_count(pdf) == 1, (
        f"Expected 1 PDF page (one chart), got {pdf_page_count(pdf)}"
    )

    if mode == "native":
        # --- Native-mode: assert deck numbers survive into the PDF text layer (REQ-C-22) ---
        # LibreOffice preserves data-label text; the PDF pool contains axis ticks and
        # data labels.  Each DECK_AIDED_AWARENESS value must appear within ±1 pp.
        nums = numbers_from_pdf(pdf)
        for brand, want in DECK_AIDED_AWARENESS.items():
            assert any(abs(want - got) <= 1.0 for got in nums), (
                f"{brand}: deck value {want}% not found in PDF numbers within ±1 — "
                f"closest was {min(nums, key=lambda g: abs(want - g)) if nums else 'none'}"
            )

    # Image mode: page count verified above; no PDF text layer for rasterized charts.


# ---------------------------------------------------------------------------
# Test 2 — Claude-as-judge (REQ-C-29b)
# ---------------------------------------------------------------------------


@pytest.mark.judge
def test_attendo_pipeline_judge(tmp_path):
    """Native-mode Attendo pipeline PDF is graded by Claude for layout quality.

    REQ-C-29b: the rendered aided-awareness chart is presentation-quality with
    clean layout, no overlapping labels, and no truncated text.
    """
    if _NO_SAV:
        pytest.skip("Attendo .sav not present")
    if _NO_SOFFICE:
        pytest.skip("soffice not on PATH")
    if _NO_API_KEY:
        pytest.skip("ANTHROPIC_API_KEY not set")

    from reportbuilder.testing.judge import judge_pdf
    from reportbuilder.testing.rubrics import rubric_for

    # --- Ingest ---
    df, model = read_sav(config.ATTENDO_SAV)
    model2, q = aided_question(model)
    # aided_question returns model2 with variables but no questions; add the question
    # so build_pptx can resolve it via model.question("aided").
    model2.questions.append(q)

    # --- Chart spec ---
    spec = ChartSpec(
        question_ref="aided",
        chart_type="horizontal_bar",
        statistic="pct",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="s1",
        elements=ElementToggles(),
    )

    report = Report(
        name="attendo-aided-judge",
        render_mode="native",
        template_ref="t.pptx",
        charts=(spec,),
    )

    pptx = build_pptx(report, model2, df, str(tmp_path / "judge_deck.pptx"))
    pdf = pptx_to_pdf(pptx, str(tmp_path))

    # --- Judge every page ---
    verdicts = judge_pdf(pdf, rubric_for("REQ-C-29b"), requirement_id="REQ-C-29b")
    failed = [v for v in verdicts if not v.passed]
    assert not failed, (
        f"Judge found {len(failed)}/{len(verdicts)} failing page(s):\n"
        + "\n".join(f"  page {i}: {v.reasoning}" for i, v in enumerate(failed))
    )
