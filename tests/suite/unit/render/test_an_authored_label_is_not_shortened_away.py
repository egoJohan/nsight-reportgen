"""The legend draws the category labels as they are, never bare scale points.

"Legendin arvojen teksteissä on vielä pientä epätarkkuutta. Category labelsin
määritys ei siirry oikein legendiin." (Suomalainen Työ, 2026-09-23)

`_legend_below` used to cut a numeric rating scale — "1 - Erittäin huono",
"2", … "7 - Erittäin hyvä" — to 1 2 3 4 5 6 7 and move the endpoint words to a
caption at the foot. Category labels went on listing the words, so the slide
and its settings disagreed, and retyping a label changed nothing: a label equal
to the data's own is not stored as an override, so the shortener never stood
down. Every exception the rule grew was a place where it had thrown away words
somebody needed: the series legend's age bands (2026-09-09), Prima Pet's money
bands ("20–40 euroa / kuukausi" drawn as "20"), an author's rename
(2026-09-16). Now nothing is shortened, and what Category labels lists is what
the legend says.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import pytest
from matplotlib.figure import Figure
from pptx import Presentation
from pptx.util import Inches

from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, SortSpec,
)
from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.stats.series import Cell, SeriesResult

pytestmark = pytest.mark.unit

#: The real scale from the reported slide.
_LEVELS = ("1 - Ei kovin tärkeä", "2", "3", "4", "5", "6", "7 - Erittäin tärkeä")
_GROUPS = ("Suomi", "Ruotsi", "Saksa")


def _series(levels=_LEVELS) -> SeriesResult:
    cells = {}
    for i, lvl in enumerate(levels):
        for j, g in enumerate(_GROUPS):
            cells[(lvl, g)] = Cell(pct=float(10 + i + j))
    return SeriesResult(
        categories=tuple(levels), segments=_GROUPS, cells=cells,
        base_n={"Total": 2968, **{g: 985 for g in _GROUPS}}, statistic="pct")


def _legend_texts(levels=_LEVELS, overrides=()) -> list[str]:
    spec = ChartSpec(
        question_ref="q1", chart_type="stacked_horizontal_bar", statistic="pct",
        classifying_var="country", number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles(title=True, subtitle=True, legend=True, n=True,
                                axis_names=True, filter_var=True, data_labels=True),
        category_label_overrides=tuple(overrides))
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=_series(levels),
        fmt=spec.number_format)

    seen: list[str] = []
    original = Figure.savefig

    def spy(self, *a, **k):
        self.canvas.draw()
        for axes in self.axes:
            leg = axes.get_legend()
            if leg is not None:
                seen.extend(t.get_text() for t in leg.get_texts())
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS["stacked_horizontal_bar"](ctx)
    finally:
        Figure.savefig = original
    return seen


def test_the_reported_scale_keeps_its_words():
    """The reported slide: endpoints worded, middle points their own number."""
    levels = ("1 - Erittäin huono", "2", "3", "4", "5", "6", "7 - Erittäin hyvä")
    assert _legend_texts(levels=levels) == list(levels)


def test_an_untouched_numeric_scale_is_drawn_as_its_labels():
    assert _legend_texts() == list(_LEVELS)


def test_a_renamed_level_is_shown_as_the_author_wrote_it():
    texts = _legend_texts(
        levels=("Ei tärkeä", "2", "3", "4", "5", "6", "7 - Erittäin tärkeä"),
        overrides=[["1 - Ei kovin tärkeä", "Ei tärkeä"]])
    assert texts == ["Ei tärkeä", "2", "3", "4", "5", "6", "7 - Erittäin tärkeä"]


def test_a_rename_that_keeps_its_number_still_shows():
    """Both old and new used to shorten to "1", so the slide never moved."""
    texts = _legend_texts(
        levels=("1 - Ei tärkeä", "2", "3", "4", "5", "6", "7 - Erittäin tärkeä"),
        overrides=[["1 - Ei kovin tärkeä", "1 - Ei tärkeä"]])
    assert texts[0] == "1 - Ei tärkeä", texts


@pytest.mark.parametrize("levels", [
    ("20–40 euroa / kuukausi", "40–60 euroa / kuukausi", "60–100 euroa / kuukausi"),
    ("alle 20 euroa", "20–40 euroa", "40–60 euroa", "yli 60 euroa"),
    ("18-24 vuotias", "25-34 vuotias", "35-44 vuotias", "45-54 vuotias"),
])
def test_bands_keep_their_ranges(levels):
    """A band's first number is not its name: "20–40 euroa" is not "20"."""
    assert _legend_texts(levels=levels) == list(levels)


def test_a_scale_the_data_numbers_itself_stays_numbers():
    """1..7 labelled only at the ends is charted as its points and the editor
    lists "1".."7" (`_partial_scale`), so the legend drawing them agrees."""
    levels = tuple(str(n) for n in range(1, 8))
    assert _legend_texts(levels=levels) == list(levels)
