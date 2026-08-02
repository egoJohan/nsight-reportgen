"""The slide subtitle line — the question text plus, on a stacked bar, the scale's
endpoint gloss ("1 = … · 5 = …").

The gloss is only the DEFAULT: an authored `slide_description` owns the whole line.
A battery's levels come from its FIRST member with a parseable scale, so once several
questions are merged into one battery the gloss describes only one of them and the
author must be able to reword it. (customer, 2026-07-31)
"""
from __future__ import annotations

from reportbuilder.render.image.slide_chrome import add_image_slide_chrome
from reportbuilder.stats.engine import scale_endpoint_gloss
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import make_ctx


_LEVELS = ("1 - En lainkaan houkuttelevana", "2", "3", "4",
           "5 - Erittäin houkuttelevana")
_GLOSS = "1 = En lainkaan houkuttelevana · 5 = Erittäin houkuttelevana"


def _stacked_series() -> SeriesResult:
    cells = {(lvl, "Väite A"): Cell(pct=20.0, count=1.0, mean=None) for lvl in _LEVELS}
    return SeriesResult(categories=_LEVELS, segments=("Väite A",), cells=cells,
                        base_n={"Total": 5, "Väite A": 5}, statistic="pct")


def _texts(slide) -> list[str]:
    return [s.text_frame.text for s in slide.shapes if s.has_text_frame]


def _subtitle_of(**spec_overrides) -> list[str]:
    _prs, slide, _slot, ctx = make_ctx(
        "stacked_horizontal_bar", _stacked_series(), **spec_overrides)
    ctx.title = "Arvioi seuraavia asteikolla 1-5"
    add_image_slide_chrome(ctx)
    return _texts(slide)


# ---- the pure helper -------------------------------------------------------
def test_gloss_reads_both_labelled_endpoints():
    assert scale_endpoint_gloss(_LEVELS) == _GLOSS


def test_gloss_empty_when_scale_is_not_numeric():
    assert scale_endpoint_gloss(("Kyllä", "Ei", "En osaa sanoa")) == ""


def test_gloss_empty_when_no_endpoint_carries_wording():
    assert scale_endpoint_gloss(("1", "2", "3", "4", "5")) == ""


# ---- the default line ------------------------------------------------------
def test_stacked_bar_appends_the_gloss_by_default():
    """No authored subtitle → question text + gloss, so the bare-number legend
    still reads."""
    texts = _subtitle_of(slide_title="Uusi pakkaus koetaan sopivaksi")
    assert any(_GLOSS in t and "Arvioi seuraavia asteikolla 1-5" in t for t in texts)


# ---- an authored subtitle owns the whole line ------------------------------
def test_authored_subtitle_suppresses_the_auto_gloss():
    """Regression: the gloss used to be appended even to an authored subtitle, so a
    battery-wide rewording still trailed the first member's wording."""
    mine = "Arvioi seuraavia asteikolla 1-5, jossa 1 = heikoin ja 5 = paras"
    texts = _subtitle_of(slide_title="Uusi pakkaus koetaan sopivaksi",
                         slide_description=mine)
    assert mine in texts
    assert not any(_GLOSS in t for t in texts)


def test_authored_subtitle_can_drop_the_gloss_entirely():
    texts = _subtitle_of(slide_title="Uusi pakkaus koetaan sopivaksi",
                         slide_description="Arvioi seuraavia asteikolla 1-5")
    assert "Arvioi seuraavia asteikolla 1-5" in texts
    assert not any("houkuttelevana" in t for t in texts)
