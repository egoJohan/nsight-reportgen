"""Small multiples as a grid, and numbers that lose their "%" when short of room.

(Johan, 2026-09-26) "Small multiples, one row" and "Small multiples, grid" are
separate choices of the variable layout — the grid draws the panels in two
rows, each twice as wide. And "remove the percentage from the number when we
are short in space": at each step a number keeps its "%" if it fits with it and
loses it only if that is what makes it fit.
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


def _var(name, labels):
    return Variable(name=name, label=name, measurement="nominal", missing_values=[],
                    value_labels=[ValueLabel(value=float(c), label=l) for c, l in labels.items()])


def _draw(n_answers, first, second=None, layout="small_multiples", nf=None):
    from reportbuilder.export.pptx_build import build_pptx
    import os
    import tempfile

    answers = {i: f"Vastaus {i}" for i in range(1, n_answers + 1)}
    rows = [{"q": float(1 + i % n_answers), "a": float(1 + (i // n_answers) % len(first)),
             "b": float(1 + (i // 13) % len(second or {1: ""}))} for i in range(3000)]
    variables = {"q": _var("q", answers), "a": _var("a", first)}
    if second:
        variables["b"] = _var("b", second)
    model = QuestionModel(variables=variables,
                          questions=[Question(qid="q", text="Q?", kind="single", variables=("q",))])
    chart = {"question_ref": "q", "chart_type": "vertical_bar", "statistic": "pct",
             "classifying_var": "a", "classifying_var_2": "b" if second else None,
             "number_format": nf or {}, "template_slot": "s1", "elements": {},
             "sort": {"basis": "data_order"}, "options": {"xtab_layout": layout}}
    report = report_from_json({"name": "r", "render_mode": "image", "template_ref": "",
                               "charts": [chart]})
    seen = []
    orig = Figure.savefig

    def spy(self, *a, **k):
        self.canvas.draw()
        labels = [t for ax in self.axes for t in ax.texts if t.get_gid() == VALUE_GID]
        seen.append({"rows": len({round(ax.get_position().y0, 3) for ax in self.axes
                                  if ax.get_visible()}),
                     "labels": [t.get_text() for t in labels],
                     "rotations": {t.get_rotation() for t in labels}})
        return orig(self, *a, **k)

    Figure.savefig = spy
    try:
        with tempfile.TemporaryDirectory() as d:
            build_pptx(report, model, pd.DataFrame(rows), os.path.join(d, "s.pptx"))
    finally:
        Figure.savefig = orig
    return seen[-1]


_FOUR = {1: "Mies", 2: "Nainen", 3: "Muu", 4: "En halua vastata"}
_FIVE = {i: f"Alue {i}" for i in range(1, 6)}


def test_one_row_draws_the_panels_side_by_side():
    assert _draw(7, _FOUR, _FIVE, "small_multiples")["rows"] == 1


def test_the_grid_draws_them_in_two_rows():
    assert _draw(7, _FOUR, _FIVE, "small_multiples_grid")["rows"] == 2


def test_numbers_that_fit_with_their_sign_keep_it():
    """Three wide columns: room for "43 %" flat — drawn exactly as before."""
    f = _draw(3, {1: "A", 2: "B"})
    assert f["labels"] and all(t.endswith("%") for t in f["labels"])
    assert f["rotations"] == {0.0}


def test_short_of_room_the_sign_goes_before_the_number_turns():
    """Six answers x five groups: too narrow for "17 %" upright, wide enough for
    "17" — upright, without the sign, rather than on its side with it."""
    f = _draw(6, {i: f"R{i}" for i in range(1, 6)})
    assert f["labels"]
    assert f["rotations"] == {0.0}
    assert not any(t.endswith("%") for t in f["labels"]), f["labels"][:6]


def test_on_its_side_a_number_keeps_its_sign_if_it_fits():
    """Seven answers x six groups: not even "17" fits upright, and on its side
    "17 %" fits — so it stands, sign and all. The sign goes last."""
    f = _draw(7, {i: f"R{i}" for i in range(1, 7)})
    assert f["labels"]
    assert f["rotations"] == {90.0}
    assert all(t.endswith("%") for t in f["labels"]), f["labels"][:6]


def test_an_author_who_turned_the_sign_off_is_not_overruled():
    f = _draw(3, {1: "A", 2: "B"}, nf={"show_pct_sign": False})
    assert f["labels"] and not any(t.endswith("%") for t in f["labels"])
