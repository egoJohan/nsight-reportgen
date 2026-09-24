"""A bar chart split by two classifying variables still shows its numbers.

"Kun vertical barissa laittaa 2 luokittelevaa muuttujaa, niin palkkien
numeroarvot katoavat kuvasta. Tämä tapahtuu riippumatta siitä onko
tunnuslukuna prosentit vai lukumäärä." (AnonyymiYhtiö, 2026-09-24)

Two classifiers draw one panel per group of the first — small multiples, or
side by side with "separate" — and both layouts drew bars and nothing else:
the value labels lived only in the one-panel renderers. Now every panel's bars
carry their numbers by the same rules as a single chart, and on a horizontal
chart the number at the end of the longest bar stays inside its own panel.
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

#: The reported slide's own answers: long enough to take the left side and make
#: every panel narrow, which is when the axis numbers met.
_ANSWER = {1: "En harkitsisi Kodin tietoturvan hankintaa osana kuvattua palvelua.",
           2: "Kyllä. Harkitsisin Kodin tietoturvan hankintaa osana kuvattua palvelua."}
_AGE = {1: "18-24", 2: "25-34", 3: "35-44", 4: "45-54", 5: "55-64", 6: "65-"}
_GENDER = {1: "Nainen", 2: "Mies"}


def _var(name, labels):
    return Variable(name=name, label=name, measurement="nominal", missing_values=[],
                    value_labels=[ValueLabel(value=float(c), label=l) for c, l in labels.items()])


def _model():
    # Six age panels, as on the reported slide, and counts into the hundreds, so a
    # narrow panel's axis reads 0 50 100 150 and its neighbour's starts at 0.
    rows = [{"q": float(1 + i % 2), "ika": float(1 + (i // 2) % 6), "sp": float(1 + (i // 12) % 2)}
            for i in range(2880)]
    model = QuestionModel(
        variables={"q": _var("q", _ANSWER), "ika": _var("ika", _AGE), "sp": _var("sp", _GENDER)},
        questions=[Question(qid="q", text="Harkitsisitko?", kind="single", variables=("q",))])
    return model, pd.DataFrame(rows)


def _touching(r, texts):
    """Pairs of axis numbers on one row whose boxes meet — "150" then "0" reads "1500"."""
    boxes = sorted(((t.get_window_extent(r), t.get_text()) for t in texts), key=lambda b: b[0].x0)
    return [(a[1], b[1]) for a, b in zip(boxes, boxes[1:])
            if a[0].x1 + 1 > b[0].x0 and a[0].y1 > b[0].y0 and b[0].y1 > a[0].y0]


def _figures(chart_type, statistic, layout):
    """For each figure saved while building the slide: its bar count, the value
    labels it drew, and those running past their own panel's right edge."""
    from reportbuilder.export.pptx_build import build_pptx

    model, df = _model()
    chart = {"question_ref": "q", "chart_type": chart_type, "statistic": statistic,
             "classifying_var": "ika", "classifying_var_2": "sp", "number_format": {},
             "template_slot": "s1", "elements": {}, "sort": {"basis": "data_order"},
             "options": {"xtab_layout": layout}}
    report = report_from_json({"name": "r", "render_mode": "image", "template_ref": "",
                               "charts": [chart]})
    seen = []
    original = Figure.savefig

    def spy(self, *a, **k):
        # Measured HERE: the renderer frees the figure once it is saved.
        from matplotlib.container import BarContainer
        self.canvas.draw()
        r = self.canvas.get_renderer()
        labels = [t for ax in self.axes for t in ax.texts
                  if t.get_gid() == VALUE_GID and t.get_visible()]
        seen.append({
            "bars": sum(len(c) for ax in self.axes for c in ax.containers
                        if isinstance(c, BarContainer)),
            "labels": [t.get_text() for t in labels],
            "outside": [t.get_text() for t in labels
                        if t.get_window_extent(r).x1 > t.axes.get_window_extent(r).x1 + 1],
            "ticks_touching": _touching(r, [t for ax in self.axes for t in ax.get_xticklabels()
                                            if t.get_visible() and t.get_text()]),
        })
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            build_pptx(report, model, df, os.path.join(d, "s.pptx"))
    finally:
        Figure.savefig = original
    return seen


@pytest.mark.parametrize("layout", ["small_multiples", "separate"])
@pytest.mark.parametrize("statistic", ["pct", "count"])
@pytest.mark.parametrize("chart_type", ["vertical_bar", "horizontal_bar"])
def test_every_bar_carries_its_number(chart_type, statistic, layout):
    [fig] = _figures(chart_type, statistic, layout)
    assert fig["labels"], f"{chart_type} {statistic} {layout}: no numbers at all"
    assert len(fig["labels"]) == fig["bars"], (len(fig["labels"]), fig["bars"])


@pytest.mark.parametrize("layout", ["small_multiples", "separate"])
def test_a_horizontal_number_stays_inside_its_panel(layout):
    [fig] = _figures("horizontal_bar", "pct", layout)
    assert fig["labels"] and not fig["outside"], fig["outside"]


@pytest.mark.parametrize("layout", ["small_multiples", "separate"])
@pytest.mark.parametrize("statistic", ["pct", "count"])
def test_the_panels_axis_numbers_do_not_run_together(statistic, layout):
    [fig] = _figures("horizontal_bar", statistic, layout)
    assert not fig["ticks_touching"], fig["ticks_touching"]


def test_narrow_panels_thin_their_axis_numbers_until_they_part():
    """The reported slide's shape: six panels in a row, each about 1.3in, every
    value axis 0 50 100 150 — one panel's "150" printed into the next one's "0"."""
    import matplotlib.pyplot as plt

    from reportbuilder.render.image.bars import _thin_panel_ticks

    fig, axes = plt.subplots(1, 6, figsize=(8.5, 3.0), sharey=True)
    fig.subplots_adjust(left=0.05, right=0.98, wspace=0.12)
    for ax in axes:
        ax.barh([0, 1], [95, 119])
        ax.set_xlim(0, 150)
        ax.set_xticks([0, 50, 100, 150], ["0", "50", "100", "150"], fontsize=9.5)
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    texts = lambda: [t for ax in axes for t in ax.get_xticklabels() if t.get_visible() and t.get_text()]
    assert _touching(r, texts()), "the setup no longer reproduces the collision"
    _thin_panel_ticks(fig, list(axes))
    fig.canvas.draw()
    assert not _touching(r, texts()), _touching(r, texts())
    assert all(ax.get_xticklabels()[0].get_text() == "0" for ax in axes), "every axis starts at 0"
    plt.close(fig)
