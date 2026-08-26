"""A rating battery honours a SECOND classifying variable.

The spec asks for two classifiers in one chart ("esimerkiksi sukupuolen ja iän
mukaan"). Both battery paths resolved segments from the PRIMARY classifier
only, so a second one was silently ignored — which is why the editor hid the
control for a battery rather than let somebody configure a chart that would
render as an ordinary one-classifier split.

Built the same way as test_battery_crosstab.py, with a second classifier added.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine

pytestmark = pytest.mark.unit


def _rating(name, label, n=5):
    return Variable(name=name, label=label, measurement="scale",
                    value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, n + 1)),
                    missing_values=frozenset())


def _setup(rows=400):
    s1 = _rating("s1", "Laadukkuus")
    s2 = _rating("s2", "Modernius")
    sukupuoli = Variable(
        name="sukupuoli", label="Sukupuoli", measurement="categorical",
        value_labels=(ValueLabel(1.0, "Mies"), ValueLabel(2.0, "Nainen")),
        missing_values=frozenset())
    ika = Variable(
        name="ika", label="Ikä", measurement="categorical",
        value_labels=(ValueLabel(1.0, "Nuori"), ValueLabel(2.0, "Vanha")),
        missing_values=frozenset())
    model = QuestionModel(
        variables={"s1": s1, "s2": s2, "sukupuoli": sukupuoli, "ika": ika},
        questions=[])
    q = Question(qid="b", kind="battery", variables=("s1", "s2"), text="Battery")
    quarter = rows // 4
    df = pd.DataFrame({
        "s1": [5.0] * quarter * 2 + [1.0] * quarter * 2,
        "s2": [4.0] * quarter * 2 + [2.0] * quarter * 2,
        "sukupuoli": [1.0] * quarter * 2 + [2.0] * quarter * 2,
        "ika": ([1.0] * quarter + [2.0] * quarter) * 2,
    })
    return model, q, df


def _spec(chart_type, cv="sukupuoli", cv2=None, statistic="pct"):
    return ChartSpec(
        question_ref="b", chart_type=chart_type, statistic=statistic,
        classifying_var=cv, classifying_var_2=cv2,
        number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
        template_slot="s", elements=ElementToggles())


def test_the_mean_battery_crosses_both_classifiers():
    model, q, df = _setup()
    one = engine.compute(q, _spec("horizontal_bar"), df, model)
    two = engine.compute(q, _spec("horizontal_bar", cv2="ika"), df, model)

    assert len(two.segments) > len(one.segments), (
        "a second classifier must add segments, not be ignored")
    crossed = [s for s in two.segments if " · " in s]
    assert set(crossed) == {"Mies · Nuori", "Mies · Vanha",
                            "Nainen · Nuori", "Nainen · Vanha"}


def test_the_stacked_battery_crosses_both_classifiers():
    model, q, df = _setup()
    two = engine.compute(q, _spec("stacked_horizontal_bar", cv2="ika"), df, model)
    assert any("Mies · Nuori" in s for s in two.segments + two.categories), (
        f"expected the crossed groups somewhere in {two.segments} / {two.categories}")


def test_the_primary_classifier_clusters_first():
    """Primary-major, the same ordering the single and multi paths use: a
    reader groups by the variable they named first."""
    model, q, df = _setup()
    two = engine.compute(q, _spec("horizontal_bar", cv2="ika"), df, model)
    heads = [s.split(" · ")[0] for s in two.segments if " · " in s]
    runs = [h for i, h in enumerate(heads) if i == 0 or heads[i - 1] != h]
    assert len(runs) == len(set(runs)), f"primary interleaved: {heads}"


def test_one_classifier_is_untouched():
    """The fallback path is what every existing battery chart renders."""
    model, q, df = _setup()
    one = engine.compute(q, _spec("horizontal_bar"), df, model)
    assert set(one.segments) >= {"Mies", "Nainen"}
    assert not any(" · " in s for s in one.segments)


def test_an_empty_combo_is_dropped_not_charted_as_zero():
    """Crossing multiplies groups; a cell nobody falls into is an artefact of
    crossing, not a finding."""
    model, q, df = _setup()
    df = df.copy()
    df.loc[df["sukupuoli"] == 1.0, "ika"] = 1.0     # no "Mies · Vanha" left
    two = engine.compute(q, _spec("horizontal_bar", cv2="ika"), df, model)
    assert "Mies · Vanha" not in two.segments


def test_a_stale_second_classifier_falls_back_rather_than_losing_the_split():
    model, q, df = _setup()
    two = engine.compute(q, _spec("horizontal_bar", cv2="no_such_column"), df, model)
    assert set(two.segments) >= {"Mies", "Nainen"}
