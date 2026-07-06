"""End-to-end: percent_base='auto' resolves the direction from variable roles,
against the synthetic crosstab fixture (gender × 7-segment × 1–7 opinion)."""
from __future__ import annotations

import pathlib

from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.report import (
    ChartSpec, NumberFormat, SortSpec, ElementToggles,
)
from reportbuilder.stats.engine import compute

FIXTURE = pathlib.Path(__file__).parents[3] / "rb" / "data" / "sav" / "synthetic_crosstab.sav"


def _spec(question_ref, classifying_var, percent_base="auto"):
    return ChartSpec(question_ref=question_ref, chart_type="horizontal_bar",
                     statistic="pct", classifying_var=classifying_var,
                     number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                     template_slot="s", elements=ElementToggles(),
                     percent_base=percent_base)


def test_auto_gender_by_segment_distributes_within_each_gender():
    df, model = read_sav(str(FIXTURE))
    q = model.question("sukupuoli")  # base = demographic gender, classifier = segment
    r = compute(q, _spec("sukupuoli", "segmentti"), df, model)
    # Gender outranks the derived segment → "question": within each gender the 7
    # segments form a distribution (≈100%). "% of men in each segment."
    for gender in ("Mies", "Nainen"):
        total = sum((r.cell(gender, s).pct or 0) for s in r.segments if s != "Total")
        assert 99.0 <= total <= 101.0, f"{gender} segments sum={total}"


def test_auto_opinion_by_gender_distributes_within_each_gender():
    df, model = read_sav(str(FIXTURE))
    q = model.question("vaittama1")  # base = Likert opinion, classifier = gender
    r = compute(q, _spec("vaittama1", "sukupuoli"), df, model)
    # Gender outranks the Likert item → "classifier" (legacy): within each gender
    # the answer options form a distribution (≈100%). "of women, X% agree."
    for gender in ("Mies", "Nainen"):
        total = sum((r.cell(cat, gender).pct or 0) for cat in r.categories)
        assert 99.0 <= total <= 101.0, f"{gender} answers sum={total}"
