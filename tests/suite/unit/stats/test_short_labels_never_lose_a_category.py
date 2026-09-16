"""Two categories given the same short label must not become one.

Found while reproducing the combo line defect. A category-label override is a
DISPLAY name, but the result is keyed by label — categories, cells and bases all
— so two categories renamed to the same string collapsed into one dict entry and
a whole category left the chart with nothing said about it:

    vertical_bar   categories=('Suuressa', 'Suuressa', 'Muu')
                   values    =[18.0, 18.0, 31.0]

The 50 % category is gone and 18 % is printed twice. On the reported city-size
slide that is why the first bar read 13 % where the unsorted chart read 32 %.

Every chart type, not just combo — and in more than one place. `_relabelled` is
the obvious one, but each question kind also renames its own members as it
builds them (`_single`'s value labels, `_multi`'s options, a battery's
statements and attributes), so fixing the shared tail alone left the single and
multi paths still collapsing. `_clash_free` is applied at each.

The rule: an override that would make two categories share a label is not
applied to the ones that clash — they keep their full names. Renaming is a
convenience, and a convenience may not cost a category. Keeping the full name
also makes the ambiguity visible to the author, where silently merging (or
silently dropping) hides it. (Johan, 2026-09-16)
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

_A = "Suuressa kaupungissa (yli 150 000 asukasta)"
_B = "Suuressa kaupungissa (100 000 - 150 000 asukasta)"
_C = "Pienessä kunnassa"


def _study():
    rng = np.random.default_rng(1)
    n = 1000
    code = rng.choice([1, 2, 3], size=n, p=[.5, .2, .3]).astype(float)
    var = Variable("q", "Kysymys", "categorical",
                   (ValueLabel(1.0, _A), ValueLabel(2.0, _B), ValueLabel(3.0, _C)),
                   frozenset())
    model = QuestionModel(variables={"q": var}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text="Kysymys")
    return model, q, pd.DataFrame({"q": code})


def _spec(chart_type="vertical_bar", **kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type=chart_type, statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s1",
                elements=ElementToggles(), options={})
    base.update(kw)
    return ChartSpec(**base)


def _run(**kw):
    model, q, df = _study()
    return engine.compute(q, _spec(**kw), df, model)


@pytest.mark.parametrize("chart_type",
                         ["vertical_bar", "horizontal_bar", "pie", "line"])
def test_no_category_is_lost_to_a_clashing_short_label(chart_type):
    """The defect, on every chart that renames anything."""
    plain = _run(chart_type=chart_type)
    short = _run(chart_type=chart_type,
                 category_label_overrides=[[_A, "Suuressa"], [_B, "Suuressa"]])
    assert len(short.categories) == len(plain.categories)
    assert len(set(short.categories)) == len(short.categories), (
        f"two categories share a label and collapsed: {short.categories}")


def test_the_values_are_the_ones_the_data_has():
    plain = _run()
    short = _run(category_label_overrides=[[_A, "Suuressa"], [_B, "Suuressa"]])
    seg = short.segments[0]
    assert (sorted(short.cell(c, seg).pct for c in short.categories)
            == sorted(plain.cell(c, plain.segments[0]).pct
                      for c in plain.categories))


def test_a_clashing_override_leaves_the_full_names():
    short = _run(category_label_overrides=[[_A, "Suuressa"], [_B, "Suuressa"]])
    assert _A in short.categories and _B in short.categories


def test_only_the_clashing_ones_are_left_alone():
    """A rename that is unambiguous still applies, in the same chart."""
    short = _run(category_label_overrides=[[_A, "Suuressa"], [_B, "Suuressa"],
                                           [_C, "Pieni"]])
    assert "Pieni" in short.categories
    assert _A in short.categories and _B in short.categories


def test_a_short_label_clashing_with_an_untouched_category_is_refused():
    """The clash need not be between two RENAMED categories — renaming one onto
    the name of a category nobody touched loses one just the same."""
    short = _run(category_label_overrides=[[_A, _C]])
    assert len(set(short.categories)) == 3
    assert _C in short.categories and _A in short.categories


def test_an_ordinary_rename_still_works():
    short = _run(category_label_overrides=[[_A, "Iso"], [_B, "Keski"]])
    assert "Iso" in short.categories and "Keski" in short.categories
    assert _A not in short.categories


# ---- the other question kinds rename their own members ---------------------

def _multi_study():
    """A multi-response set whose two options would shorten to one name."""
    rng = np.random.default_rng(2)
    n = 400
    vars_ = {}
    for name, label in (("m1", _A), ("m2", _B), ("m3", _C)):
        vars_[name] = Variable(name, label, "categorical",
                               (ValueLabel(1.0, "Checked"),
                                ValueLabel(0.0, "Unchecked")), frozenset())
    model = QuestionModel(variables=vars_, questions=[])
    q = Question(qid="m", kind="multi", variables=("m1", "m2", "m3"), text="Mitkä?")
    df = pd.DataFrame({k: rng.choice([0.0, 1.0], size=n) for k in vars_})
    return model, q, df


def test_a_multi_response_option_is_not_lost_to_a_clashing_label():
    model, q, df = _multi_study()
    spec = _spec(chart_type="horizontal_bar",
                 category_label_overrides=[[_A, "Suuressa"], [_B, "Suuressa"]])
    r = engine.compute(q, spec, df, model)
    assert len(r.categories) == 3, r.categories
    assert len(set(r.categories)) == 3, f"options collapsed: {r.categories}"


def test_a_multi_response_option_still_renames_when_unambiguous():
    model, q, df = _multi_study()
    spec = _spec(chart_type="horizontal_bar",
                 category_label_overrides=[[_A, "Iso"], [_B, "Keski"]])
    r = engine.compute(q, spec, df, model)
    assert "Iso" in r.categories and "Keski" in r.categories
