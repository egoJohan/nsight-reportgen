"""A cross-tab asked for ONE group of its first classifier does not repeat it.

"Haluaisimme poistaa legendistä arvon 2026." A slide split by year and by
customer segment, but asked for 2026 only (`classifying_values=("2026",)`),
drew a legend of "2026 · Laatua arvostavat…", "2026 · Muut segmentit": every
entry carrying the same word, which says nothing the filter line does not
already say, and takes the width the segment names need.

The battery path already had this rule for one classifier (`sole_group`): when
the slide ASKED for one group, its name comes off the bars and the filter line
names it. The cross-tab paths — the single/multi `_relabel_combo_segments` and
the batteries' `_crossed_masks` — built "<first> · <second>" regardless. So the
rule now holds for every question kind and both cross-tab paths.

Keyed on what was asked AND what happened: a stale group (no longer in the
data) narrows nothing, every year is drawn, and then the year is the only thing
telling the series apart — so it stays. (2026-11-10)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine

pytestmark = pytest.mark.unit

_SEGS = ("Laatua arvostavat", "Muut segmentit")


def _study():
    rng = np.random.default_rng(26)
    n = 800

    def cat(name, label, *labels):
        return Variable(name, label, "categorical",
                        tuple(ValueLabel(float(i + 1), lb) for i, lb in enumerate(labels)),
                        frozenset())

    def rating(name, label):
        return Variable(name, label, "scale",
                        tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)), frozenset())

    vars_ = [
        cat("q", "Tunnetko?", "Kyllä", "Ei"),
        cat("year", "Ajankohta", "2025", "2026"),
        cat("seg", "Segmentti", *_SEGS),
        cat("m1", "Synsam", "Checked"), cat("m2", "Nissen", "Checked"),
        rating("s1", "Laadukkuus"), rating("s2", "Modernius"),
    ]
    model = QuestionModel(variables={v.name: v for v in vars_}, questions=[])
    df = pd.DataFrame({
        "q": rng.choice([1.0, 2.0], n),
        "year": rng.choice([1.0, 2.0], n),
        "seg": rng.choice([1.0, 2.0], n),
        "m1": rng.choice([0.0, 1.0], n), "m2": rng.choice([0.0, 1.0], n),
        "s1": rng.integers(1, 6, n).astype(float), "s2": rng.integers(1, 6, n).astype(float),
    })
    questions = {
        "single": Question(qid="q", kind="single", variables=("q",), text="Tunnetko?"),
        "multi": Question(qid="m", kind="multi", variables=("m1", "m2"), text="Mitkä?"),
        "battery": Question(qid="b", kind="battery", variables=("s1", "s2"), text="Väitteet"),
    }
    return model, questions, df


def _compute(kind, chart_type="horizontal_bar", **kw):
    model, questions, df = _study()
    q = questions[kind]
    base = dict(question_ref=q.qid, chart_type=chart_type, statistic="pct",
                classifying_var="year", classifying_var_2="seg",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles())
    base.update(kw)
    return engine.compute(q, ChartSpec(**base), df, model)


# (question kind, chart type) — every cross-tab path: single/multi through
# `_relabel_combo_segments`, the mean battery and the stacked battery through
# `_crossed_masks`.
_CASES = [
    ("single", "horizontal_bar"),
    ("single", "vertical_bar"),
    ("multi", "horizontal_bar"),
    ("battery", "horizontal_bar"),
    ("battery", "stacked_horizontal_bar"),
]


def _names(r):
    """Every name a series or a bar carries on the slide."""
    return tuple(r.segments) + tuple(r.categories)


@pytest.mark.parametrize("kind,chart_type", _CASES)
def test_one_asked_year_is_not_in_any_series_name(kind, chart_type):
    r = _compute(kind, chart_type, classifying_values=("2026",))
    assert not any("2026" in s for s in _names(r)), _names(r)
    # ...and the segments are still there, under their own names
    assert all(any(seg in s for s in _names(r)) for seg in _SEGS), _names(r)


@pytest.mark.parametrize("kind,chart_type", _CASES)
def test_a_year_the_author_renamed_keeps_its_name(kind, chart_type):
    """A slide saved with "2026" renamed to "Vuosi 2026" drew that text before
    this rule existed; the author meant it to be read, so it stays."""
    r = _compute(kind, chart_type, classifying_values=("2026",),
                 series_label_overrides=(("2026", "Vuosi 2026"),))
    assert all("Vuosi 2026 · " in s for s in r.segments if s != "Total"), r.segments


@pytest.mark.parametrize("kind,chart_type", _CASES)
def test_the_filter_line_still_names_the_year(kind, chart_type):
    r = _compute(kind, chart_type, classifying_values=("2026",))
    assert r.applied_filter == ("2026",)


@pytest.mark.parametrize("kind,chart_type", _CASES)
def test_two_asked_years_keep_the_year_in_the_names(kind, chart_type):
    """Two years drawn: the year is what tells "2025 · X" from "2026 · X"."""
    r = _compute(kind, chart_type, classifying_values=("2025", "2026"))
    assert any("2025" in s for s in _names(r)) and any("2026" in s for s in _names(r))


@pytest.mark.parametrize("kind,chart_type", _CASES)
def test_a_stale_asked_year_narrows_nothing_and_keeps_the_names(kind, chart_type):
    r = _compute(kind, chart_type, classifying_values=("2019",))
    assert any("2025" in s for s in _names(r)) and any("2026" in s for s in _names(r))


@pytest.mark.parametrize("kind", ["single", "multi"])
def test_one_asked_year_is_not_grouped_by_year(kind):
    """One group is no grouping: the renderer must not pull the bars into one
    "2026" cluster or print "2026" above them."""
    r = _compute(kind, classifying_values=("2026",))
    assert not r.segment_primary


@pytest.mark.parametrize("kind", ["single", "multi"])
def test_the_numbers_are_the_years_numbers(kind):
    """Dropping the name drops nothing else: each series is still that year's
    segment, cell for cell."""
    one = _compute(kind, classifying_values=("2026",))
    both = _compute(kind, classifying_values=("2025", "2026"))
    for seg in _SEGS:
        for cat in one.categories:
            assert one.cells[(cat, seg)].pct == both.cells[(cat, f"2026 · {seg}")].pct


# --- A space typed over a name blanks it --------------------------------------
#
# "Jos legendin tekstimäärittelyssä tekstin "2026" paikalle muuttaa pelkän
# välilyönnin, kuva ei päivity." The engine threw a spaces-only rename away as
# if it were empty, so the chart kept the name the editor no longer showed.

@pytest.mark.parametrize("kind", ["single", "multi", "battery"])
def test_a_part_renamed_to_a_space_leaves_the_name(kind):
    r = _compute(kind, classifying_values=("2025", "2026"),
                 series_label_overrides=(("2026", " "),))
    names = _names(r)
    assert not any("2026" in s for s in names), names
    # the blanked part takes its separator with it, and 2025 is untouched
    assert all(not s.startswith(" · ") and " ·  · " not in s for s in names), names
    assert any("2025 · " in s for s in names), names


def test_a_plain_series_renamed_to_a_space_is_drawn_blank():
    r = _compute("single", classifying_var_2=None,
                 series_label_overrides=(("2026", " "),))
    assert "2026" not in r.segments and "" in r.segments
    assert "2025" in r.segments


def test_an_empty_rename_is_no_rename():
    r = _compute("single", classifying_var_2=None,
                 series_label_overrides=(("2026", ""),))
    assert "2026" in r.segments


def test_blanking_two_series_keeps_both_names():
    """Two blanks would be one key: the clash rule keeps both as they were."""
    r = _compute("single", classifying_var_2=None,
                 series_label_overrides=(("2025", " "), ("2026", " ")))
    assert {"2025", "2026"} <= set(r.segments)
