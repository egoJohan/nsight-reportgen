"""A headline for a combo is written from both of its measures.

"Combo chartin otsikko ja alaotsikko ei mukaudu molempiin kuvaajiin. Vain
ykköstyypin kuvaajaan."

The title endpoint could not see the second measure at all. `SlideTitleBody`
carried no chart type and no options, and `_spec_from_title_body` hard-coded
`chart_type="horizontal_bar"` with none — so `_compute_series`'s combo branch
(`chart_type == "combo" and options["combo_secondary"]`) never ran, and the
series the prompt was built from had no secondary segment in it. The model was
not ignoring the line; it had never been told the line exists.

Two things then had to be right before it could be:

* `_findings_from_series` short-circuits on a "Total" column and reads every
  cell with ONE statistic, `series.statistic`. A two-variable combo parks the
  secondary MEAN in the `pct` field on purpose, so a 1-8 index would have been
  read as a percentage and then ranked against real percentages in one sorted
  list — a headline claiming 6.1 beat 19 %.
* A mean and a percentage cannot share a ranking at all, so the line's findings
  are labelled with what they are rather than merged into the ordering.

(Johan, 2026-09-16)
"""
from __future__ import annotations

import pytest

from reportbuilder.api.routes_ai import (
    SlideTitleBody, _findings_from_series, _spec_from_title_body,
)
from reportbuilder.stats.series import Cell, SeriesResult

pytestmark = pytest.mark.unit

_CATS = ("Suuressa", "Keskisuuressa", "Pienessä")
_INDEX = "index_johtaminenjakulttuuri"


def _combo_series() -> SeriesResult:
    """What `_combo_two_var` produces: bars in pct, the line's MEAN in `pct`."""
    cells = {}
    for i, c in enumerate(_CATS):
        cells[(c, "Total")] = Cell(pct=float(32 - i * 6))     # 32, 26, 20 %
        cells[(c, _INDEX)] = Cell(pct=float(5.6 + i * 0.3))   # 5.6, 5.9, 6.2
    return SeriesResult(
        categories=_CATS, segments=("Total", _INDEX), cells=cells,
        base_n={"Total": 1043, _INDEX: 1043}, statistic="pct",
        segment_statistics={"Total": "pct", _INDEX: "mean"})


# ---- the spec the engine is given ------------------------------------------

def test_the_chart_type_reaches_the_engine():
    spec = _spec_from_title_body(SlideTitleBody(
        question_ref="q", chart_type="combo",
        options={"combo_secondary": _INDEX}))
    assert spec.chart_type == "combo"


def test_the_secondary_variable_reaches_the_engine():
    spec = _spec_from_title_body(SlideTitleBody(
        question_ref="q", chart_type="combo",
        options={"combo_secondary": _INDEX}))
    assert spec.options.get("combo_secondary") == _INDEX


def test_a_body_that_names_neither_is_unchanged():
    """Every existing caller sends neither, and must get what it got before."""
    spec = _spec_from_title_body(SlideTitleBody(question_ref="q"))
    assert spec.chart_type == "horizontal_bar"
    assert not spec.options


# ---- what the model is told -------------------------------------------------

def test_a_mean_is_not_ranked_against_percentages():
    """32 % and 6.2 are not comparable, and sorting them together put the
    index above or below bars it has no relation to."""
    findings = _findings_from_series(_combo_series(), top_n=5)
    values = [v for _label, v in findings]
    pct = [v for label, v in findings if _INDEX not in label]
    assert pct == sorted(pct, reverse=True), values


def test_the_secondary_findings_are_present():
    """The whole point: the model can only describe what it is given."""
    findings = _findings_from_series(_combo_series(), top_n=5)
    assert any(_INDEX in label for label, _v in findings), findings


def test_the_secondary_findings_say_what_they_are():
    """Labelled, so a 6.2 is not read as 6.2 %."""
    findings = _findings_from_series(_combo_series(), top_n=5)
    secondary = [label for label, _v in findings if _INDEX in label]
    assert secondary and all("keskiarvo" in l.lower() or "mean" in l.lower()
                             for l in secondary), secondary


def test_the_bars_are_still_the_top_findings():
    """The question is still what the slide is about; the line is context."""
    findings = _findings_from_series(_combo_series(), top_n=3)
    assert _INDEX not in findings[0][0], findings


def test_an_ordinary_series_is_unchanged():
    """No segment statistics — every existing chart type."""
    cells = {(c, "Total"): Cell(pct=float(30 - i * 5)) for i, c in enumerate(_CATS)}
    plain = SeriesResult(categories=_CATS, segments=("Total",), cells=cells,
                         base_n={"Total": 500}, statistic="pct")
    assert _findings_from_series(plain, top_n=3) == [
        ("Suuressa", 30.0), ("Keskisuuressa", 25.0), ("Pienessä", 20.0)]


# ---- the prompt -------------------------------------------------------------

def test_the_prompt_explains_a_second_measure_when_there_is_one():
    from reportbuilder.ai.text import _slide_title_prompt

    prompt = _slide_title_prompt(
        "Minkä kokoisessa kaupungissa asut?",
        _findings_from_series(_combo_series(), top_n=3))
    assert "(keskiarvo)" in prompt
    assert "ei prosenttiosuus" in prompt


def test_an_ordinary_chart_prompt_is_unchanged():
    """Byte-identical for every chart with one measure — the note is added only
    where it applies, so no existing headline changes."""
    from reportbuilder.ai.text import _slide_title_prompt

    findings = [("Suuressa", 32.0), ("Pienessä", 20.0)]
    prompt = _slide_title_prompt("Kysymys?", findings)
    assert "keskiarvo" not in prompt
