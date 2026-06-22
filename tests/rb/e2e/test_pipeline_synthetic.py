"""Full-pipeline E2E — synthetic SAV through ingest → model → report → build_pptx →
pptx_to_pdf, asserting number fidelity in native and image render modes.

Charts in this E2E:
  1. q1  — single-choice question (Yes/No), statistic="pct"
  2. m   — multi-group question (m1 + m2 binary tick-boxes), statistic="pct"

DEFERRED (engine limitation):
  A third chart for the scale variable ``age`` (statistic="mean") is intentionally
  omitted.  The statistics engine's ``compute`` function builds chart categories by
  enumerating a variable's ``value_labels``; a pure scale variable (no value labels)
  yields an empty SeriesResult, and the ``mean`` statistic is not wired into the
  engine's ``compute`` path.  This chart kind is deferred pending engine support for
  mean/scale series (REQ-C-15 follow-up).  Do NOT modify the engine in this task.

Fidelity architecture notes (relevant to the assertions below):

  (A) PPTX / numbers_from_pptx collision: ``numbers_from_pptx`` keys extracted
      series values by *series name*.  Both q1 and the multi chart produce a segment
      named ``"Total"``, so the second chart's values overwrite the first in the
      returned dict.  The raw PPTX DOES contain correct data on both slides (verified
      by per-slide inspection), but the extraction utility cannot surface both without
      a dict-key collision.  Consequence: the PPTX pool-based check is reliable only
      for the multi chart (last in the file).  For the q1 chart the PPTX pool is used
      as a best-effort check; the authoritative per-chart verification is the native
      PDF text layer (see B).

  (B) Native PDF / numbers_from_pdf: LibreOffice converts native PPTX to PDF while
      preserving data-label text as selectable PDF text.  The native PDF text pool
      contains axis ticks and data labels from BOTH slides, making it the reliable
      combined fidelity check for native mode.

  (C) Image PDF / numbers_from_pdf: Image mode renders each chart as a matplotlib
      PNG embedded in the slide.  LibreOffice cannot extract text from a raster PNG,
      so ``numbers_from_pdf`` returns an empty list for image-mode PDFs.  The PDF
      text-layer assertion is therefore restricted to native mode; image mode verifies
      page count only (REQ-C-21) and relies on the preceding native-mode run for
      value fidelity coverage.

Requirements covered: REQ-C-18, REQ-C-21, REQ-C-22, REQ-C-28b.
"""
from __future__ import annotations

import os
import shutil

import pytest

from reportbuilder.export.pdf_convert import pptx_to_pdf, pdf_page_count
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.ingest.multi_group import suggest_multi_groups, apply_groups
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
)
from reportbuilder.stats.engine import compute
from reportbuilder.testing.fidelity import (
    assert_series_match,
    numbers_from_pdf,
    numbers_from_pptx,
)
from reportbuilder.testing.fixtures import synthetic_sav

# ---------------------------------------------------------------------------
# Skip guards
# ---------------------------------------------------------------------------

_NO_SOFFICE = shutil.which("soffice") is None
_NO_API_KEY = not os.environ.get("ANTHROPIC_API_KEY")

_skip_soffice = pytest.mark.skipif(_NO_SOFFICE, reason="soffice not on PATH")
_skip_api_key = pytest.mark.skipif(_NO_API_KEY, reason="ANTHROPIC_API_KEY not set")


# ---------------------------------------------------------------------------
# Chart-spec builder
# ---------------------------------------------------------------------------

def _chart_spec(question_ref: str, slot: str) -> ChartSpec:
    return ChartSpec(
        question_ref=question_ref,
        chart_type="vertical_bar",
        statistic="pct",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot=slot,
        elements=ElementToggles(),
    )


# ---------------------------------------------------------------------------
# Test 1 — objective fidelity (both render modes)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["native", "image"])
def test_pipeline_synthetic_both_modes(mode, tmp_path):
    """Full pipeline: synthetic SAV → PPTX → PDF, number fidelity in native + image mode.

    REQ-C-18: completed deck contains all requested charts (2 slides).
    REQ-C-21: PDF is produced and its page count matches the chart count.
    REQ-C-22: rendered data values (pct) match the engine-computed series within tolerance.
    """
    # --- Ingest ---
    path = synthetic_sav(tmp_path)
    df, model = read_sav(path)

    # --- Group m1+m2 into one multi question ---
    groups = suggest_multi_groups(model)
    model = apply_groups(model, groups)

    # Sanity: model must contain exactly q1 (single) + multi question for m1/m2.
    questions_by_qid = {q.qid: q for q in model.questions}
    assert "q1" in questions_by_qid, "q1 question missing from grouped model"
    multi_questions = [q for q in model.questions if q.kind == "multi"]
    assert len(multi_questions) == 1, f"Expected 1 multi question, got {len(multi_questions)}"
    multi_q = multi_questions[0]
    assert set(multi_q.variables) == {"m1", "m2"}, (
        f"Multi question variables should be {{m1, m2}}, got {set(multi_q.variables)}"
    )

    q1_qid = questions_by_qid["q1"].qid   # "q1"
    multi_qid = multi_q.qid               # "m" (derived from prefix of m1)

    # --- Build 2-chart report ---
    report = Report(
        name="synthetic-e2e",
        render_mode=mode,
        template_ref="t.pptx",
        charts=(
            _chart_spec(q1_qid, "slot1"),
            _chart_spec(multi_qid, "slot2"),
        ),
    )

    # --- Build PPTX ---
    pptx = build_pptx(report, model, df, str(tmp_path / "deck.pptx"))
    assert os.path.isfile(pptx), f"build_pptx did not produce a file: {pptx}"

    # --- Convert to PDF (skip if soffice absent) ---
    if shutil.which("soffice") is None:
        pytest.skip("soffice not on PATH — PDF conversion skipped")

    pdf = pptx_to_pdf(pptx, str(tmp_path))
    assert os.path.isfile(pdf), f"pptx_to_pdf did not produce a file: {pdf}"

    # --- Page count == number of charts (REQ-C-21) ---
    assert pdf_page_count(pdf) == 2, (
        f"Expected 2 PDF pages (one per chart), got {pdf_page_count(pdf)}"
    )

    # --- Compute engine series for fidelity checks (REQ-C-22) ---
    q1_question = model.question(q1_qid)
    q1_spec = report.charts[0]
    series_q1 = compute(q1_question, q1_spec, df, model)

    multi_question = model.question(multi_qid)
    multi_spec = report.charts[1]
    series_multi = compute(multi_question, multi_spec, df, model)

    if mode == "native":
        # --- Native-mode PPTX chart-data check ---
        # numbers_from_pptx keys by series name; both charts produce a "Total"
        # segment so only the last chart's values survive in the dict (see module
        # docstring note A).  We assert both series against the flat pool — this
        # catches the multi chart values reliably; for q1 the PDF check below is
        # the authoritative verification.
        pptx_pool = numbers_from_pptx(pptx)
        assert_series_match(pptx_pool, series_multi)

        # --- Native-mode PDF text-layer check (authoritative combined check) ---
        # LibreOffice preserves data-label text; the PDF pool contains axis ticks
        # and data labels from ALL slides, covering both charts (see note B).
        pdf_nums = numbers_from_pdf(pdf)
        assert_series_match({"pdf": pdf_nums}, series_q1)
        assert_series_match({"pdf": pdf_nums}, series_multi)

    # Image mode: page count already verified above; PDF text layer is empty for
    # rasterized image-mode charts (see module docstring note C) — no further
    # number assertion is possible.  Native mode run above provides value-fidelity
    # coverage for REQ-C-22.


# ---------------------------------------------------------------------------
# Test 2 — Claude-as-judge (REQ-C-28b)
# ---------------------------------------------------------------------------

@pytest.mark.judge
@_skip_soffice
@_skip_api_key
def test_pipeline_synthetic_judge(tmp_path):
    """Native-mode full pipeline PDF is graded by Claude for layout quality.

    REQ-C-28b: the rendered report is presentation-quality with clean layout,
    no overlapping labels, and no truncated text.
    """
    from reportbuilder.testing.judge import judge_pdf
    from reportbuilder.testing.rubrics import rubric_for

    # --- Ingest + group ---
    path = synthetic_sav(tmp_path)
    df, model = read_sav(path)
    model = apply_groups(model, suggest_multi_groups(model))

    multi_q = next(q for q in model.questions if q.kind == "multi")
    q1_qid = "q1"
    multi_qid = multi_q.qid

    # --- Build native report ---
    report = Report(
        name="synthetic-judge",
        render_mode="native",
        template_ref="t.pptx",
        charts=(
            _chart_spec(q1_qid, "slot1"),
            _chart_spec(multi_qid, "slot2"),
        ),
    )
    pptx = build_pptx(report, model, df, str(tmp_path / "judge_deck.pptx"))

    pdf = pptx_to_pdf(pptx, str(tmp_path))

    # --- Judge every page ---
    verdicts = judge_pdf(pdf, rubric_for("REQ-C-28b"), requirement_id="REQ-C-28b")
    failed = [v for v in verdicts if not v.passed]
    assert not failed, (
        f"Judge found {len(failed)}/{len(verdicts)} failing page(s):\n"
        + "\n".join(f"  page {i}: {v.reasoning}" for i, v in enumerate(failed))
    )
