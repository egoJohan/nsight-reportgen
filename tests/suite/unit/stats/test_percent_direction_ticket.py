"""Ticket: cross-tab percentage DIRECTION (gender × values-segment).

Reproduces the customer report ("Ristiintaulukointi-prosenteilla"): on a chart
whose base variable is a demographic (gender) split by a values SEGMENT, the
percentages go the misleading way when percent_base == "classifier" — each
SEGMENT sums to 100% across gender ("of segment X, 50% are women"), which does
NOT match the count chart's message. The wanted reading (and what "auto" already
resolves to) is "question": each GENDER sums to 100% across the segments
("of women, X% are in segment Y").

Fixture: rb/data/sav/synthetic_crosstab.sav (gender × 7-segment × 1–7 opinion) —
the same structure as the customer's chart.
"""
from __future__ import annotations

import pathlib

from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.report import ChartSpec, NumberFormat, SortSpec, ElementToggles
from reportbuilder.stats.engine import compute
from reportbuilder.stats.percent_base import resolve_percent_base

FIXTURE = pathlib.Path(__file__).parents[3] / "rb" / "data" / "sav" / "synthetic_crosstab.sav"


def _spec(base, clf, percent_base):
    return ChartSpec(question_ref=base, chart_type="horizontal_bar", statistic="pct",
                     classifying_var=clf, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s",
                     elements=ElementToggles(), percent_base=percent_base)


def test_classifier_direction_is_the_reported_wrong_reading():
    """percent_base='classifier' → each SEGMENT sums to 100% across gender, and the
    genders do NOT sum to 100% — the misleading chart the customer flagged."""
    df, model = read_sav(str(FIXTURE))
    q = model.question("sukupuoli")               # base = gender, classifier = segment
    r = compute(q, _spec("sukupuoli", "segmentti", "classifier"), df, model)
    # Each segment (a classifier group) sums to ~100% across the genders.
    for seg in r.segments:
        if seg == "Total":
            continue
        across_gender = sum((r.cell(g, seg).pct or 0) for g in r.categories)
        assert 99.0 <= across_gender <= 101.0, f"segment {seg} across gender = {across_gender}"
    # …and therefore a single gender's segments do NOT form a distribution.
    men_segments = sum((r.cell("Mies", s).pct or 0) for s in r.segments if s != "Total")
    assert men_segments > 130, f"men segments sum={men_segments} (should be far from 100)"


def test_question_direction_is_the_wanted_reading():
    """percent_base='question' → each GENDER sums to 100% across the segments
    ("of women, X% are in segment Y") — the direction the ticket asks for."""
    df, model = read_sav(str(FIXTURE))
    q = model.question("sukupuoli")
    r = compute(q, _spec("sukupuoli", "segmentti", "question"), df, model)
    for gender in ("Mies", "Nainen"):
        seg_total = sum((r.cell(gender, s).pct or 0) for s in r.segments if s != "Total")
        assert 99.0 <= seg_total <= 101.0, f"{gender} segments sum={seg_total}"


def test_auto_already_resolves_to_the_wanted_direction():
    """The current auto-resolution ALREADY picks 'question' for gender(base) ×
    segment(classifier) — so the reported chart must have percent_base pinned to
    'classifier' rather than 'auto'. This documents where the fix belongs."""
    df, model = read_sav(str(FIXTURE))
    q = model.question("sukupuoli")
    spec = _spec("sukupuoli", "segmentti", "auto")
    assert resolve_percent_base(q, spec, model) == "question"
