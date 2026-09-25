"""The author-warning channel is tested where its two halves MEET.

Both ends were covered and the wire between them was not. One test built a
`RenderContext(notes=[...])` by hand and called a builder directly; another
patched `build_pptx` with a stub that appended the note itself. Each was tested
against a fake of the other, so deleting `notes=notes` from `deck.py` — one
keyword — disabled every author warning repo-wide with 1506 tests still green.
Measured, by doing it.

The same single point of failure carries `X-Chart-Empty`'s sibling mechanism and
every note kind added later, so it is worth a test that goes all the way
through: a real report, a real builder, a real note.

Its companion pins the other end — WHAT the deck asks for when a chart has
nothing to plot. `render_empty_chart` still accepts a message and draws it; only
its default is empty, and the only test of that calls the function itself. One
word at the call site puts "No data to show" back across a Finnish client's
slide, which is the defect the whole change was written to remove.
(Johan, 2026-09-17)
"""
from __future__ import annotations


import matplotlib
matplotlib.use("Agg")
import pytest

from reportbuilder.export.pptx_build import build_presentation
from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, Report, SortSpec,
)
from reportbuilder.render.base import RenderNote
from reportbuilder.render.image import _mpl
from reportbuilder.testing.fixtures import tiny_model_and_data

pytestmark = pytest.mark.integration


def _report(**over) -> Report:
    base = dict(question_ref="q1", chart_type="horizontal_bar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s1",
                elements=ElementToggles())
    base.update(over)
    return Report(name="r", render_mode="image", template_ref="",
                  charts=(ChartSpec(**base),))


def test_a_note_raised_while_drawing_reaches_the_caller(monkeypatch):
    """The wire itself: `build_presentation(notes=…)` -> deck -> ctx -> `note()`.

    The REAL builder raises the note; only the threshold moves, so every bar is
    "too thin to label" and the warning fires on an ordinary chart. Stubbing the
    builder would have re-created the hole this test exists to close — a fake at
    one end of the wire proves nothing about the wire.
    """
    from reportbuilder.render.image import bars

    monkeypatch.setattr(bars, "_MIN_LABEL_BAR_PT", 10_000.0)
    # And the second chance a thin bar now gets, once measured (2026-09-25):
    # without this the chart is numbered after all and nothing is raised.
    monkeypatch.setattr(bars, "_VALUE_LABEL_SIDE_MIN_PT", 10_000.0)

    model, df = tiny_model_and_data()
    notes: list[RenderNote] = []
    build_presentation(_report(), model, df, notes=notes)
    assert [n.kind for n in notes] == ["unlabelled"], (
        "the note never left the builder — check that deck.py still hands "
        f"`notes` to the RenderContext it builds; got {notes!r}")


def test_nobody_collecting_is_still_fine(monkeypatch):
    """The deck export passes no list. A builder that raised regardless would
    crash every path that does not want the answer."""
    from reportbuilder.render.image import bars

    monkeypatch.setattr(bars, "_MIN_LABEL_BAR_PT", 10_000.0)
    # And the second chance a thin bar now gets, once measured (2026-09-25):
    # without this the chart is numbered after all and nothing is raised.
    monkeypatch.setattr(bars, "_VALUE_LABEL_SIDE_MIN_PT", 10_000.0)
    model, df = tiny_model_and_data()
    build_presentation(_report(), model, df)   # must not raise


def test_the_deck_asks_for_a_blank_placeholder(monkeypatch):
    """What `deck.py` PASSES, not what the default is.

    A chart with nothing to plot draws a blank space. The message argument still
    exists for a caller that wants text; the deck must never be that caller.
    """
    asked: list[str] = []
    real = _mpl.render_empty_chart

    def spy(ctx, message: str = ""):
        asked.append(message)
        return real(ctx, message)

    monkeypatch.setattr("reportbuilder.render.deck.render_empty_chart", spy)

    model, df = tiny_model_and_data()
    blank = df.assign(q1=[float("nan")] * len(df))
    build_presentation(_report(), model, blank)

    assert asked, "the empty branch was never reached — the fixture is not blank"
    assert asked == [""], (
        f"the deck asked for a message on the slide: {asked!r}. What a slide "
        "could not show is a warning to its AUTHOR, raised in the editor.")
