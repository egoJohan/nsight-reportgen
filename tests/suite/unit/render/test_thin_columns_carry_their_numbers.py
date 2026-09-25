"""Thin columns still carry their numbers — on their side, sized to the bar.

"Kun vertical barissa laittaa 2 luokittelevaa muuttujaa, niin palkkien
numeroarvot katoavat kuvasta." (2026-09-25, still.) Two classifiers make many
thin columns: five regions in each of seven answers, twice over (ylpeys ×
Sukupuoli × maakuntaluokka), or eight gender × answer combinations in one panel.
Past a point (about 4pt-wide columns) no number is readable; then there are
none and the author is told — including in the one-panel layout, which used to
say nothing, and which sized its numbers before its legend narrowed the plot.
A number on its side was asked for a full LINE of room across its column at
7.5pt — about 10pt — when the digits themselves are about 5pt tall, so every
number on the chart was dropped. A number on its side now takes the height of
its own digits, shrinking with the column down to 5pt.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import pandas as pd
import pytest
from matplotlib.figure import Figure

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import report_from_json
from reportbuilder.render.image._mpl import VALUE_GID

pytestmark = pytest.mark.unit

_SCALE = {1: "1- Ei lainkaan ylpeä", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7- Erittäin ylpeä"}
_REGION = {1: "Uusimaa", 2: "Muu Etelä-Suomi", 3: "Länsi-Suomi", 4: "Itä-Suomi", 5: "Pohjois-Suomi"}
_SEX = {1: "Mies", 2: "Nainen", 3: "Muu", 4: "En halua vastata"}
_SEX2 = {1: "Mies", 2: "Nainen"}
_CAN = {1: "Kyllä voin", 2: "En voi"}


def _var(name, labels):
    return Variable(name=name, label=name, measurement="nominal", missing_values=[],
                    value_labels=[ValueLabel(value=float(c), label=l) for c, l in labels.items()])


def _model(second: dict, first: dict = _SEX):
    rows = [{"q": float(1 + i % 7), "a": float(1 + (i // 7) % len(first)),
             "b": float(1 + (i // 31) % len(second))} for i in range(2928)]
    model = QuestionModel(
        variables={"q": _var("q", _SCALE), "a": _var("a", first), "b": _var("b", second)},
        questions=[Question(qid="q", text="Kuinka ylpeä?", kind="single", variables=("q",))])
    return model, pd.DataFrame(rows)


def _figure(second: dict, statistic: str, layout: str, first: dict = _SEX, notes=None):
    from reportbuilder.export.pptx_build import build_pptx

    model, df = _model(second, first)
    chart = {"question_ref": "q", "chart_type": "vertical_bar", "statistic": statistic,
             "classifying_var": "a", "classifying_var_2": "b", "number_format": {},
             "template_slot": "s1", "elements": {}, "sort": {"basis": "data_order"},
             "options": {"xtab_layout": layout}}
    report = report_from_json({"name": "r", "render_mode": "image", "template_ref": "",
                               "charts": [chart]})
    seen = []
    original = Figure.savefig

    def spy(self, *a, **k):
        from matplotlib.container import BarContainer
        self.canvas.draw()
        r = self.canvas.get_renderer()
        heights = [b.get_height() for ax in self.axes for c in ax.containers
                   if isinstance(c, BarContainer) for b in c]
        labels = [t for ax in self.axes for t in ax.texts
                  if t.get_gid() == VALUE_GID and t.get_visible()]
        seen.append({"bars": sum(1 for h in heights if h > 0),
                     "labels": labels, "boxes": [t.get_window_extent(r) for t in labels],
                     "sizes": [t.get_fontsize() for t in labels], "dpi": self.dpi,
                     "above_plot": [t.get_text() for t in labels
                                    if t.get_window_extent(r).y1 > t.axes.get_window_extent(r).y1 + 1]})
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            build_pptx(report, model, df, os.path.join(d, "s.pptx"),
                       notes=notes if notes is not None else [])
    finally:
        Figure.savefig = original
    return seen[-1]


_THREE = {1: "0", 2: "Alle 25v töissä", 3: "Alle 25v opiskelee"}

CASES = [
    # image 3: five regions per answer, a panel per gender
    pytest.param(_REGION, "small_multiples", _SEX2, id="2-panels-x5x7"),
    pytest.param(_REGION, "separate", _SEX2, id="2-separate-x5x7"),
    # images 4-5: four genders x can/cannot, eight combinations in ONE panel
    pytest.param(_CAN, "grouped", _SEX, id="8-combos-one-panel"),
]


@pytest.mark.parametrize("statistic", ["pct", "count"])
@pytest.mark.parametrize("second,layout,first", CASES)
def test_every_column_carries_its_number(second, layout, first, statistic):
    f = _figure(second, statistic, layout, first)
    assert f["bars"] > 0
    assert len(f["labels"]) >= f["bars"], (len(f["labels"]), f["bars"])
    assert min(f["sizes"]) >= 5.0


@pytest.mark.parametrize("statistic", ["pct", "count"])
@pytest.mark.parametrize("second,layout,first", CASES)
def test_neighbouring_numbers_do_not_overlap(second, layout, first, statistic):
    """Side by side on their sides, their DIGITS must not meet: the distance
    between two neighbours' centres is at least the height of the digits. (The
    text boxes are a line tall, wider than the digits, so they may overlap.)"""
    from reportbuilder.render.image.bars import _ink_height_in

    f = _figure(second, statistic, layout, first)
    items = sorted(zip(f["boxes"], f["labels"]), key=lambda p: p[0].x0)
    dpi = f["dpi"]
    for (a, ta), (b, tb) in zip(items, items[1:]):
        if a.y1 > b.y0 and b.y1 > a.y0:  # at the same height
            ink_px = max(_ink_height_in(ta.get_text(), ta.get_fontsize()),
                         _ink_height_in(tb.get_text(), tb.get_fontsize())) * dpi
            gap = (b.x0 + b.x1) / 2 - (a.x0 + a.x1) / 2
            assert gap >= ink_px, (ta.get_text(), tb.get_text(), gap, ink_px)


@pytest.mark.parametrize("layout,first,second", [
    ("small_multiples", _SEX, _REGION),   # four panels of five: 3.6pt-wide bars
    ("grouped", _SEX, _REGION),           # twenty combinations in one panel
    ("grouped", _SEX, _THREE),            # twelve in one panel, legend at the right
])
def test_too_thin_to_number_says_so(layout, first, second):
    """Past a point the columns are too thin for any number a reader could read
    (3-4pt wide). Then none — and the author is TOLD, in every layout. The
    one-panel layout used to drop them without a word."""
    notes: list = []
    f = _figure(second, "pct", layout, first, notes=notes)
    assert f["labels"] == []
    assert any(getattr(n, "kind", None) == "unlabelled" for n in notes), notes


_plain_model = _model


def _one_full_column(second, first=_SEX):
    """Every answer 1 in one group of the panel classifier: a 100 % column."""
    model, df = _plain_model(second, first)
    df.loc[df["a"] == 2.0, "q"] = 1.0
    return model, df


@pytest.mark.parametrize("layout", ["small_multiples", "separate"])
def test_a_full_column_keeps_its_number_inside_its_panel(layout, monkeypatch):
    """"100 %" standing on a full-height column ran into the panel's title
    above it (found in the visual matrix, 2026-09-25). The axis is lengthened by
    the number's length, as the horizontal panels' is."""
    import sys
    mod = sys.modules[__name__]
    monkeypatch.setattr(mod, "_model", _one_full_column)
    f = _figure(_REGION, "pct", layout, _SEX2)
    assert f["labels"], "the panels should be numbered"
    assert f["above_plot"] == [], f["above_plot"]
