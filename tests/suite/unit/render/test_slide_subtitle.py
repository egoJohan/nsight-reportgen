"""The slide subtitle line is the author's, and nSight does not write into it.

It used to append a stacked bar's endpoint gloss ("1 = … · 5 = …") to the
default subtitle, so that a legend of bare numbers still read (customer,
2026-07-31). Nothing is lost by stopping, because the wording is already on the
slide in both shapes that produce it:

  * a scale whose points carry their own text ("1 - En lainkaan houkuttelevana")
    shows exactly that in the LEGEND; and
  * a scale labelled only at its ends is drawn as numbers with the wording in
    the caption above the footer.

And since an author can now name every point of an endpoint-labelled scale in
the label editor, the meaning belongs in the legend rather than in a line that
was overwritten for them. (Johan, 2026-09-05)
"""
from __future__ import annotations

from reportbuilder.render.image.slide_chrome import add_image_slide_chrome
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


# ---- the default line ------------------------------------------------------
def test_the_default_subtitle_is_the_question_and_nothing_else():
    texts = _subtitle_of(slide_title="Uusi pakkaus koetaan sopivaksi")
    assert any("Arvioi seuraavia asteikolla 1-5" in t for t in texts)
    assert not any(_GLOSS in t for t in texts)


def test_a_numbers_only_scale_still_states_its_ends_in_the_caption():
    """The shape the append existed for. When the scale is drawn as bare numbers
    the engine hands the wording over as a caption, and chrome draws it above the
    footer — so the meaning reaches the slide without touching the subtitle."""
    numbered = ("1", "2", "3", "4", "5")
    cells = {(lvl, "Väite A"): Cell(pct=20.0, count=1.0, mean=None) for lvl in numbered}
    series = SeriesResult(categories=numbered, segments=("Väite A",), cells=cells,
                          base_n={"Total": 5, "Väite A": 5}, statistic="pct",
                          caption=_GLOSS)
    _prs, slide, _slot, ctx = make_ctx("stacked_horizontal_bar", series,
                                       slide_title="Uusi pakkaus koetaan sopivaksi")
    ctx.title = "Arvioi seuraavia asteikolla 1-5"
    add_image_slide_chrome(ctx)
    texts = _texts(slide)
    assert _GLOSS in texts, "the caption is not drawn on the slide"
    # and it is its OWN line, not spliced onto the question
    assert not any(t.startswith("Arvioi") and _GLOSS in t for t in texts)


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
