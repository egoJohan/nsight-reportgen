"""The chart preview must look like the slide it is previewing.

A preview is drawn by compositing the chart onto the customer's empty slide,
which LibreOffice renders once per template instead of once per chart — 4.4s a
chart became ~0.2s. That is only worth having if the result is the same picture,
so this renders one chart BOTH ways and compares the pixels.

Exact equality is the wrong bar: LibreOffice and PIL resample and antialias
differently, so glyph edges and bar outlines land a shade apart. Layout is what
must match — a shifted chart, a different colour or a substituted typeface moves
far more than a few percent of pixels.
"""
from __future__ import annotations

import shutil

import numpy as np
import pytest
from PIL import Image

from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.pptx_build import build_pptx, build_presentation
from reportbuilder.export.preview import rasterize_pages
from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, Report, SortSpec,
)
from reportbuilder.render.base import StyleSpec
from reportbuilder.render.image import fast_preview


pytestmark = pytest.mark.skipif(
    shutil.which("soffice") is None or shutil.which("pdftoppm") is None,
    reason="LibreOffice + poppler required",
)

_DPI = 110


def _one_chart_report(ref="q"):
    spec = ChartSpec(
        question_ref=ref, chart_type="horizontal_bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        # title=False: the frontend owns the title band, which is when the
        # compositor is used.
        elements=ElementToggles(title=False),
    )
    return Report(name="p", render_mode="image", template_ref="", charts=(spec,))


@pytest.fixture(scope="module")
def survey():
    """Real survey data: an empty chart is a "no data" placeholder, which is
    mostly blank and tells us nothing about how a real chart composites."""
    from reportbuilder import config
    from reportbuilder.ingest.sav_reader import read_sav

    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo SAV not available locally")
    return read_sav(config.ATTENDO_SAV)


def _chartable_ref(df, model):
    from reportbuilder.stats.engine import compute

    for q in model.questions:
        try:
            compute(q, _one_chart_report(q.qid).charts[0], df, model)
            return q.qid
        except Exception:  # noqa: BLE001
            continue
    pytest.skip("no chartable question in the survey")


def _rendered_by_libreoffice(tmp_path, style, report, model, df):
    pptx = build_pptx(report, model, df, str(tmp_path / "deck.pptx"),
                      style=style)
    pdf = pptx_to_pdf(pptx, str(tmp_path / "pdf"))
    png = rasterize_pages(pdf, str(tmp_path / "png"), dpi=_DPI)[0]
    return Image.open(png).convert("RGB")


def _composited(style, report, model, df):
    prs = build_presentation(report, model, df, style=style)
    return fast_preview.compose_from_slide(style, prs.slides[0], dpi=_DPI)


@pytest.fixture(autouse=True)
def _fresh_ground(tmp_path, monkeypatch):
    """A cache directory of its own, so the test never reads another run's ground."""
    monkeypatch.setattr(fast_preview, "_CACHE", tmp_path / "ground")


_TEMPLATES = {
    "house": None,
    "attendo": "input/Attendo Bränditutkimus Marraskuu 2025.pptx",
    "synsam": "input/Synsam_Segmentointitutkimus_30.4.2025_nSight.pptx",
    "holidayclub": "input/Holiday Club_Loyalty tutkimus_raportti_19.2.2026.pptx",
}


def _ink_difference(theirs, ours):
    """How much of the INK differs, allowing one pixel of position.

    Ink only, because a slide is mostly background: scoring whole images called
    a bullet slide "98% identical" while its text was the wrong colour in the
    wrong place. One pixel of tolerance, because a glyph stem is 1-2px wide and
    a sub-pixel rounding difference would otherwise fail every one of them while
    looking the same to a person.
    """
    a = np.asarray(theirs.convert("L"), dtype=float)
    b = np.asarray(ours.convert("L"), dtype=float)
    ink = (np.abs(a - np.median(a)) > 25) | (np.abs(b - np.median(b)) > 25)
    best = np.full(a.shape, 1e9)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            best = np.minimum(best, np.abs(a - np.roll(np.roll(b, dy, 0), dx, 1)))
    return (best[ink] > 25).sum() / max(1, int(ink.sum())) * 100


@pytest.mark.parametrize("name", sorted(_TEMPLATES))
def test_the_composited_preview_matches_the_rendered_slide(tmp_path, name, survey):
    """Every template, not one sample: the whole point is that it is reliable.

    Measured across the four real client templates the error sits under 3% of
    inked pixels — differences confined to antialiasing on glyph and bar edges.
    """
    import pathlib as _pathlib

    path = _TEMPLATES[name]
    if path and not _pathlib.Path(path).exists():
        pytest.skip(f"{path} not available locally")
    if path:
        from reportbuilder.render.style_spec import load_style_spec
        style = load_style_spec(path)
    else:
        style = StyleSpec()

    df, model = survey
    report = _one_chart_report(_chartable_ref(df, model))
    theirs = _rendered_by_libreoffice(tmp_path, style, report, model, df)
    ours = _composited(style, report, model, df)
    assert ours is not None, "no ground was rendered — the fast path would never run"
    assert ours.size == theirs.size
    assert _ink_difference(theirs, ours) < 6.0, "the preview does not match the slide"


def test_the_ground_is_rendered_once_and_reused(tmp_path, monkeypatch, survey):
    """The whole point: LibreOffice runs per TEMPLATE, not per chart."""
    df, model = survey
    report = _one_chart_report(_chartable_ref(df, model))
    style = StyleSpec()
    calls = []
    real = fast_preview.pptx_to_pdf
    monkeypatch.setattr(fast_preview, "pptx_to_pdf",
                        lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    for _ in range(3):
        assert _composited(style, report, model, df) is not None
    assert len(calls) == 1


def test_a_missing_ground_falls_back_rather_than_guessing(monkeypatch, survey):
    """A preview that cannot be composited must say so, not invent a slide."""
    df, model = survey
    monkeypatch.setattr(fast_preview, "ground_image", lambda *a, **k: None)
    prs = build_presentation(_one_chart_report(_chartable_ref(df, model)), model, df,
                             style=StyleSpec())
    assert fast_preview.compose_from_slide(StyleSpec(), prs.slides[0]) is None


def test_a_baked_title_is_not_composited():
    """The gate, and why it is where it is.

    With the title baked into the slide the compositor is measurably worse — 4%
    to 21% of ink across the real templates, and visibly wrong on a template
    whose title is all-caps with diacritics (the diaereses detach from their
    capitals). So the preview endpoint only takes the fast path when the
    frontend owns the title band, and everything else still goes through
    LibreOffice. Widening this gate needs the measurement to come with it.
    """
    import inspect

    from reportbuilder.api import routes_questions

    source = inspect.getsource(routes_questions.preview_chart)
    assert "if not body.render_title:" in source
    fast_at = source.index("compose_from_slide")
    assert source.index("if not body.render_title:") < fast_at
