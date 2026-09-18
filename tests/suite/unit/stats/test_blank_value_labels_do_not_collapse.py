"""A value label that is present but BLANK must not merge its category with
every other blank one.

Taffel, var36 — "Minkä seuraavista sipsituotteista valitsisit ostoskoriisi?
Vaihtoehtoja on 29". The SAV declares all 29 value labels and every one of them
is the empty string. Categories are keyed by their label, so all 29 collapsed
onto "", `SeriesResult.cells` kept exactly ONE of them, and the slide drew 29
identical bars all reading that single surviving cell — 2 %, n=27 — while the
real distribution runs 110, 68, 63, 58, 52, 49, 46 ... The numbers on the slide
were wrong, not merely unlabelled, and nothing on it said so.

`code_labels` already exists for this file's sibling case and its docstring
names this very variable (Johan, 2026-09-14) — but it is reached through
`if not labels`, and a dict of 29 blank strings is not falsy. Blank labels are
no labels.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats.engine import compute

#: The real shape: 29 codes, every label blank, a plainly uneven distribution.
_COUNTS = {1.0: 110, 2.0: 30, 3.0: 41, 4.0: 22, 5.0: 35, 6.0: 27, 7.0: 44,
           8.0: 63, 9.0: 68, 10.0: 46, 11.0: 49, 12.0: 20, 13.0: 33, 14.0: 25,
           15.0: 38, 16.0: 21, 17.0: 29, 18.0: 46, 19.0: 24, 20.0: 58,
           21.0: 19, 22.0: 31, 23.0: 26, 24.0: 23, 25.0: 34, 26.0: 52,
           27.0: 18, 28.0: 28, 29.0: 40}


def _model(label_for):
    var = Variable(name="var36", label="Minkä seuraavista sipsituotteista?",
                   measurement="categorical", missing_values=[],
                   value_labels=[ValueLabel(value=c, label=label_for(c))
                                 for c in sorted(_COUNTS)])
    rows = [{"var36": c} for c, n in _COUNTS.items() for _ in range(n)]
    model = QuestionModel(
        variables={"var36": var},
        questions=[Question(qid="q36", text=var.label, kind="single",
                            variables=("var36",))])
    return model, pd.DataFrame(rows)


def _spec() -> ChartSpec:
    return ChartSpec(question_ref="q36", chart_type="horizontal_bar",
                     statistic="pct", classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())


def _series(label_for):
    model, df = _model(label_for)
    q = model.questions[0]
    return compute(q, _spec(), df, model)


def test_every_code_keeps_its_own_category_when_all_labels_are_blank():
    sr = _series(lambda c: "")
    assert len(set(sr.categories)) == len(_COUNTS), (
        "29 codes collapsed onto one category key")


def test_the_values_drawn_are_the_real_distribution_not_one_repeated_cell():
    sr = _series(lambda c: "")
    seg = sr.segments[0]
    pcts = {c: sr.cell(c, seg).pct for c in sr.categories}
    assert len(set(pcts.values())) > 1, "every bar got the same number"
    # The most-chosen code is 1.0 with 110 of 1002 answers.
    assert max(pcts.values()) == pytest.approx(11.0, abs=1.0)


def test_a_blank_label_among_real_ones_still_gets_its_own_category():
    """The partial case: one blank must not merge with another blank, and must
    not steal a labelled category either."""
    sr = _series(lambda c: "" if c in (2.0, 3.0) else f"Tuote {int(c)}")
    assert len(set(sr.categories)) == len(_COUNTS)
    seg = sr.segments[0]
    assert len({sr.cell(c, seg).count for c in sr.categories}) > 1


def test_real_labels_are_untouched():
    sr = _series(lambda c: f"Tuote {int(c)}")
    assert "Tuote 1" in set(sr.categories)
    assert len(set(sr.categories)) == len(_COUNTS)
