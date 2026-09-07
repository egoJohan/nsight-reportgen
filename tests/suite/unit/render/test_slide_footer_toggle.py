"""The methodology footer is optional; the disclosures on it are not.

`elements.n` has been in the model since the native builder drew its own "N="
textbox, and the image renderer — the one every preview and every deck goes
through — ignored it. There was no way to draw a slide without "N = 1200" on
it. (Johan, 2026-09-07)

Switching it off removes the METHODOLOGY line: the N, or whatever the author's
`footer_note` template renders. It must NOT remove the two disclosures that
ride the same line, because those are not decoration: a slide that silently
dropped a group, or that counts only some of the classifier's groups, is read
as the whole study by anyone not told otherwise, and the footer is the only
record of it that travels with the deck.
"""
from __future__ import annotations

from dataclasses import replace

from reportbuilder.render.image.slide_chrome import add_image_slide_chrome
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import make_ctx


def _series(*, applied=()) -> SeriesResult:
    cats = ("Kyllä", "Ei")
    cells = {(c, "Total"): Cell(pct=50.0, count=450.0, mean=None) for c in cats}
    return SeriesResult(categories=cats, segments=("Total",), cells=cells,
                        base_n={"Total": 900}, statistic="pct",
                        applied_filter=tuple(applied))


def _texts(series=None, **spec_overrides) -> list[str]:
    _prs, slide, _slot, ctx = make_ctx(
        "horizontal_bar", series if series is not None else _series(), **spec_overrides)
    ctx.title = "Suosittelisitko?"
    add_image_slide_chrome(ctx)
    return [s.text_frame.text for s in slide.shapes if s.has_text_frame]


def _elements(**over):
    """The default toggles with `over` applied — ElementToggles is frozen."""
    from reportbuilder.model.report import ElementToggles
    return replace(ElementToggles(), **over)


def test_the_footer_is_drawn_by_default():
    assert any("N = 900" in t for t in _texts())


def test_switching_n_off_removes_the_methodology_line():
    texts = _texts(elements=_elements(n=False))
    assert not any("N = 900" in t for t in texts), texts
    assert not any("900" in t for t in texts), "the base is still printed somewhere"
    # the slide is otherwise intact
    assert any("Suosittelisitko?" in t for t in texts)


def test_an_authored_footer_note_goes_with_it():
    texts = _texts(elements=_elements(n=False),
                   footer_note="{stat} · n = {n}")
    assert not any("Osuus vastaajista" in t for t in texts), texts


def test_the_group_selection_is_still_disclosed():
    """The slide counts only these respondents. Hiding the N does not buy the
    author the right to stop saying so."""
    texts = _texts(_series(applied=("Naiset", "25-34 vuotias")),
                   classifying_var="sex", elements=_elements(n=False))
    assert any("Naiset" in t and "25-34 vuotias" in t for t in texts), texts
    assert not any("N = 900" in t for t in texts)
