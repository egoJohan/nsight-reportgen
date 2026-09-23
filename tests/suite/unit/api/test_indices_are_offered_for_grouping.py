"""Every index on one range is offered for grouping, not just the lucky ones.

"KRIITTINEN Indeksit eivät siirry Manage grouping -osioon. Suomalaisen työn
raportissa on datassa 7 indeksiä … se tunnistaa indekseistä vain kaksi."
(2026-09-23)

The seven indices are AVERAGES on 1..10 — `index_tyojatoimeentulo` takes the
values 1, 2.5, 4, 5.5, 7, 8.5, 10 — with no value labels. `_scale_from_data`
read an unlabelled column's range off its WHOLE-number values alone and wanted
them unbroken. An index averaged over many items happened to hit every integer
1..10 and was offered; one averaged over three items hits only 1, 4, 7, 10 and
was not. Whether an index could join a battery depended on how many items it
averaged.

A column of fractional values is a score on a range, and the range is where its
values lie: lowest to highest, rounded outward to whole points. The 3..11 point
limit that keeps an age or a percentage out of the pool still applies.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from reportbuilder.api.routes_questions import _groupable_scale_rows
from reportbuilder.model.question import Variable
from reportbuilder.stats.engine import scale_levels

pytestmark = pytest.mark.unit

#: The value sets of the reported indices, as the SAV holds them.
INDICES = {
    # averaged over many items: every integer 1..10 occurs — was offered
    "index_teknologianvaikutukset": [1 + i / 3 for i in range(28)],
    # averaged over three items: steps of 1.5 — was NOT offered
    "index_tyojatoimeentulo": [1.0, 2.5, 4.0, 5.5, 7.0, 8.5, 10.0],
    # steps of 0.75 — was NOT offered
    "index_osaaminenjakehittyminen": [1 + 0.75 * i for i in range(13)],
    # the overall index: lowest answer 1.3, so 1 itself never occurs
    "tyoelamaindeksi": [1.3, 1.8, 2.625, 3.0, 4.4, 5.0, 6.35, 7.0, 8.0, 9.2, 10.0],
}


def _var(name: str) -> Variable:
    return Variable(name, name, "scale", (), frozenset())


def _df(values: dict[str, list[float]], n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    return pd.DataFrame({k: rng.choice(v, size=n) for k, v in values.items()})


def test_every_index_is_offered_on_the_same_scale():
    df = _df(INDICES)
    rows = _groupable_scale_rows([_var(n) for n in INDICES], df)
    assert all(rows[n]["scale"] for n in INDICES), {n: rows[n]["scale"] for n in INDICES}
    keys = {rows[n]["scale_compat_key"] for n in INDICES}
    assert len(keys) == 1, keys


def test_an_index_reads_as_ten_points():
    df = _df(INDICES)
    points = [p for _c, _l, p in scale_levels(_var("index_tyojatoimeentulo"), df)]
    assert points == [float(p) for p in range(1, 11)]


def test_a_fractional_column_too_wide_to_be_a_scale_is_not_one():
    """An age with decimals or a percentage is a quantity, not a rating."""
    df = _df({"ika": [18.5 + i for i in range(60)], "osuus": [0.5 * i for i in range(201)]})
    for name in ("ika", "osuus"):
        assert scale_levels(_var(name), df) == [], name


def test_integer_ratings_are_read_as_before():
    """A whole-number rating keeps the existing rule: an unbroken run of points."""
    df = _df({"q": [1.0, 2.0, 3.0, 4.0, 5.0], "gappy": [1.0, 2.0, 5.0]})
    assert [p for _c, _l, p in scale_levels(_var("q"), df)] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert scale_levels(_var("gappy"), df) == []


# ---- once grouped, a battery of indices reports the indices' real values ----

def _battery_of_indices(chart_type: str, statistic: str):
    from reportbuilder.model.question import Question, QuestionModel
    from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
    from reportbuilder.stats.engine import compute

    df = _df(INDICES)
    names = tuple(INDICES)
    model = QuestionModel(
        variables={n: _var(n) for n in names},
        questions=[Question(qid="indeksit", text="Indeksit", kind="battery", variables=names)])
    spec = ChartSpec(question_ref="indeksit", chart_type=chart_type, statistic=statistic,
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())
    return df, compute(model.questions[0], spec, df, model)


def test_a_battery_mean_is_the_mean_of_every_answer():
    """The defect behind the defect: only whole-number answers were counted."""
    df, got = _battery_of_indices("horizontal_bar", "mean")
    for name in INDICES:
        cell = got.cells[(name, "Total")]
        assert cell.count == df[name].notna().sum(), name
        assert cell.mean == pytest.approx(df[name].mean()), name


def test_a_stacked_battery_counts_every_answer():
    """Stacked, each answer lands on its nearest whole point: all are counted and
    every statement sums to 100 %."""
    df, got = _battery_of_indices("stacked_horizontal_bar", "pct")
    for name in INDICES:
        total = sum(got.cells[(lvl, name)].pct or 0 for lvl in got.categories
                    if (lvl, name) in got.cells)
        assert total == pytest.approx(100.0), (name, total)
        assert got.base_n[name] == df[name].notna().sum(), name
