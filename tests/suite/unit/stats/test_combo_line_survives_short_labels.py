"""A combo's line keeps its values when a category is given a short label.

"Kun combo chart järjestetään prosenttiosuuksien mukaan, kakkoskuvaaja (viiva)
ei piirry oikein. Numeroarvot jostain syystä eivät ole oikein."

Sorting is not the cause; it only moved the broken points somewhere visible.

`_combo_two_var` gets its categories from `_single`, which has ALREADY applied
the author's category-label overrides — so the categories are the short labels
("Suuressa kaupungissa"). It then resolved each one back to a code through a map
built from the variable's FULL value labels ("Suuressa kaupungissa (yli 150 000
asukasta)"). Every renamed category missed, took an empty set of rows, and
produced None — which `series_values` draws as 0.0. On the reported slide three
of five points sat flat on zero.

The bars were unaffected, because they come straight from `_single`. Only the
line, which is the one thing computed from the category label. (Johan, 2026-09-16)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from reportbuilder.model.question import (
    Question, QuestionModel, ValueLabel, Variable,
)
from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, SortSpec,
)
from reportbuilder.stats import engine

pytestmark = pytest.mark.unit

_CITY = (
    "Suuressa kaupungissa (yli 150 000 asukasta)",
    "Suuressa kaupungissa (100 000 - 150 000 asukasta)",
    "Keskisuuressa kaupungissa (50 000 - 100 000 asukasta)",
    "Pienessä kaupungissa (10 000 – 50 000 asukasta)",
    "Pienessä kaupungissa tai kunnassa (alle 10 000 asukasta)",
)


def _study():
    rng = np.random.default_rng(3)
    n = 1043
    city = rng.choice([1, 2, 3, 4, 5], size=n, p=[.32, .13, .19, .20, .16])
    var = Variable("q", "Minkä kokoisessa kaupungissa tai kunnassa asut?",
                   "categorical",
                   tuple(ValueLabel(float(i + 1), c) for i, c in enumerate(_CITY)),
                   frozenset())
    sec = Variable("idx", "index_johtaminenjakulttuuri", "scale", (), frozenset())
    model = QuestionModel(variables={"q": var, "idx": sec}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text=var.label)
    # A mean that differs per category, so a wrong lookup cannot pass by luck.
    df = pd.DataFrame({"q": city.astype(float), "idx": 4.0 + city * 0.5})
    return model, q, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type="combo", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s1",
                elements=ElementToggles(), options={"combo_secondary": "idx"})
    base.update(kw)
    return ChartSpec(**base)


def _line(result):
    seg = result.segments[-1]
    return {c: result.cell(c, seg).pct for c in result.categories}


def test_the_line_has_a_value_for_every_category():
    model, q, df = _study()
    r = engine.compute(q, _spec(), df, model)
    missing = [c for c, v in _line(r).items() if v is None]
    assert not missing, f"no line value for {missing}"


def test_a_short_label_does_not_empty_the_line():
    """The reported defect. Renaming a category for display must not change
    which respondents its mean is taken over."""
    model, q, df = _study()
    short = [[_CITY[0], "Suuressa kaupungissa"],
             [_CITY[4], "Pienessä kaupungissa tai kunnassa"]]
    r = engine.compute(q, _spec(category_label_overrides=short), df, model)
    line = _line(r)
    missing = [c for c, v in line.items() if v is None]
    assert not missing, f"renamed categories lost their line value: {missing}"


def test_a_renamed_category_keeps_its_own_value():
    """Not merely non-None — the SAME number it had under its full name."""
    model, q, df = _study()
    before = _line(engine.compute(q, _spec(), df, model))
    short = [[_CITY[0], "Iso kaupunki"]]
    after = _line(engine.compute(q, _spec(category_label_overrides=short), df, model))
    assert after["Iso kaupunki"] == pytest.approx(before[_CITY[0]])


def test_sorting_does_not_change_any_line_value():
    """Sorting is what made it visible, so it is worth pinning down that it
    changes the ORDER and nothing else."""
    model, q, df = _study()
    flat = _line(engine.compute(q, _spec(), df, model))
    sorted_ = _line(engine.compute(
        q, _spec(sort=SortSpec(basis="pct", descending=True)), df, model))
    assert sorted_ == pytest.approx(flat)


def test_sorted_and_renamed_together():
    """Both at once, which is what the report was looking at."""
    model, q, df = _study()
    short = [[_CITY[0], "Iso kaupunki"], [_CITY[2], "Keskikokoinen"]]
    r = engine.compute(q, _spec(sort=SortSpec(basis="pct", descending=True),
                                category_label_overrides=short), df, model)
    line = _line(r)
    assert not [c for c, v in line.items() if v is None], line
    assert len(set(line.values())) == len(line), (
        f"two categories share a line value, so a lookup landed on the wrong "
        f"rows: {line}")
