"""An author can drag the legend items into the order they want.

Order and sort are the same knob, so dragging sets the basis to "manual" and
stores the order as FULL labels — the stable identity, the same key the label
overrides use. Rename a category and its position survives; the engine's
categories are the SHORT labels, so the order is applied where both are still
in scope, by re-indexing each entry's `data_index`.

Re-indexing rather than a sort of its own is the whole point: `data_index` is
what every builder already orders by, so one change reaches a plain bar, a
multi-response, a battery — and a split pie, whose panels and shared legend all
read their categories from the same list. (Johan, 2026-09-07)
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.stats.engine import compute


def _model() -> tuple[QuestionModel, pd.DataFrame]:
    """One single-choice question, four options, plus a country to split by."""
    opts = ["Kokopäivätyössä", "Osa-aikatyössä", "Yrittäjä", "Eläkkeellä"]
    var = Variable(name="tilanne", label="Työtilanne", measurement="nominal",
                   value_labels=[ValueLabel(value=float(i + 1), label=o)
                                 for i, o in enumerate(opts)],
                   missing_values=[])
    maa = Variable(name="maa", label="Maa", measurement="nominal",
                   value_labels=[ValueLabel(value=1.0, label="Suomi"),
                                 ValueLabel(value=2.0, label="Ruotsi")],
                   missing_values=[])
    rows = []
    for i in range(200):
        rows.append({"tilanne": float(i % 4 + 1), "maa": float(i % 2 + 1)})
    df = pd.DataFrame(rows)
    model = QuestionModel(
        variables={"tilanne": var, "maa": maa},
        questions=[Question(qid="tilanne", text="Työtilanne", kind="single",
                            variables=("tilanne",)),
                   Question(qid="maa", text="Maa", kind="single",
                            variables=("maa",))])
    return model, df


def _spec(chart_type="horizontal_bar", *, order=(), basis="manual",
          overrides=(), classifier=None) -> ChartSpec:
    return ChartSpec(
        question_ref="tilanne", chart_type=chart_type, statistic="pct",
        classifying_var=classifier, number_format=NumberFormat(),
        sort=SortSpec(basis=basis, manual_order=tuple(order)),
        template_slot="s1", elements=ElementToggles(),
        category_label_overrides=tuple(overrides))


def _categories(spec) -> list[str]:
    model, df = _model()
    return list(compute(model.question("tilanne"), spec, df, model).categories)


DRAGGED = ("Eläkkeellä", "Kokopäivätyössä", "Yrittäjä", "Osa-aikatyössä")


def test_without_a_manual_order_nothing_changes():
    assert _categories(_spec(basis="data_order")) == [
        "Kokopäivätyössä", "Osa-aikatyössä", "Yrittäjä", "Eläkkeellä"]


def test_the_dragged_order_is_the_drawn_order():
    assert _categories(_spec(order=DRAGGED)) == list(DRAGGED)


def test_a_renamed_category_keeps_its_place():
    """The order is stored as FULL labels, so shortening one does not move it."""
    cats = _categories(_spec(order=DRAGGED,
                             overrides=(("Kokopäivätyössä", "Kokopäivä"),)))
    assert cats == ["Eläkkeellä", "Kokopäivä", "Yrittäjä", "Osa-aikatyössä"]


def test_a_category_the_order_does_not_name_goes_to_the_tail():
    """A re-imported dataset can carry an option the stored order never saw. It
    must still be drawn — behind the named ones, in its own data order."""
    cats = _categories(_spec(order=("Eläkkeellä", "Yrittäjä")))
    assert cats[:2] == ["Eläkkeellä", "Yrittäjä"]
    assert cats[2:] == ["Kokopäivätyössä", "Osa-aikatyössä"]


def test_a_name_the_data_no_longer_has_is_ignored():
    cats = _categories(_spec(order=("Ei ole enää", "Eläkkeellä")))
    assert cats[0] == "Eläkkeellä"
    assert "Ei ole enää" not in cats


def test_the_manual_order_beats_a_frequency_sort_it_was_dragged_over():
    """Dragging sets basis="manual"; a leftover "pct" would silently re-sort."""
    assert _categories(_spec(order=DRAGGED, basis="manual")) == list(DRAGGED)


# --- multi-charts ----------------------------------------------------------
def test_a_split_pie_gives_every_panel_the_dragged_order():
    """One panel per country. The categories are shared — the wedge order and
    the one legend beneath them both come from this list."""
    spec = _spec("pie", order=DRAGGED, classifier="maa")
    model, df = _model()
    series = compute(model.question("tilanne"), spec, df, model)
    assert list(series.categories) == list(DRAGGED)
    # and every panel really carries all four, in that order
    for seg in ("Suomi", "Ruotsi"):
        assert [c for c in series.categories
                if series.cell(c, seg) is not None] == list(DRAGGED)
