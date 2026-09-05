"""The percentage direction is chosen, not guessed.

"Automatic" was an option that decided nothing: it resolved to the same
direction every time, whichever way round the variables were. The old
role-scoring behind it had been removed as guessing wrong too often, but the
name stayed — so an author who saw "Automatic" believed the tool had worked
something out about their variables, and a reader of the finished slide had no
way to tell 64 % ("of women, this many are Digiturva 0") from 44 % ("of the
Digiturva 0 group, this many are women").

The direction it always landed on remains the default, so no report that exists
changes its numbers. Only the label stops making a claim.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.config_schema import percent_base_field
from reportbuilder.stats import engine


def _model():
    dig = Variable(name="dig", label="Onko Digiturva 1/0", measurement="categorical",
                   value_labels=(ValueLabel(0.0, "0"), ValueLabel(1.0, "1")),
                   missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Female"), ValueLabel(2.0, "Male")),
                   missing_values=frozenset())
    return QuestionModel(
        variables={"dig": dig, "sex": sex},
        questions=[Question(qid="dig", kind="single", variables=("dig",),
                            text="Onko Digiturva 1/0")])


def _df():
    return pd.DataFrame({
        "dig": [0.0] * 640 + [1.0] * 360 + [0.0] * 818 + [1.0] * 230,
        "sex": [1.0] * 1000 + [2.0] * 1048,
    })


def _pcts(**over):
    base = dict(question_ref="dig", chart_type="vertical_bar", statistic="pct",
                classifying_var="sex", number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(over)
    model = _model()
    r = engine.compute(model.question("dig"), ChartSpec(**base), _df(), model)
    return {(c, s): round(r.cell(c, s).pct) for c in r.categories
            for s in r.segments if s != "Total"}


def test_the_offered_directions_no_longer_include_a_decision_nobody_makes():
    values = {v for v, _label in percent_base_field().options}
    assert "auto" not in values
    assert values == {"classifier", "question", "total"}


def test_the_default_is_the_one_automatic_always_landed_on():
    assert percent_base_field().default == "classifier"
    assert ChartSpec.__dataclass_fields__["percent_base"].default == "classifier"


def test_a_new_chart_percentages_within_each_classifying_group():
    got = _pcts()
    assert got[("0", "Female")] == 64 and got[("1", "Female")] == 36
    assert got[("0", "Male")] == 78 and got[("1", "Male")] == 22


def test_a_report_saved_with_automatic_still_renders_the_same_numbers():
    """Every report written before this change carries percent_base="auto"."""
    assert _pcts(percent_base="auto") == _pcts(percent_base="classifier")


def test_the_other_direction_is_still_a_setting_away():
    got = _pcts(percent_base="question")
    assert got[("0", "Female")] == 44 and got[("0", "Male")] == 56
    assert got[("1", "Female")] == 61 and got[("1", "Male")] == 39
