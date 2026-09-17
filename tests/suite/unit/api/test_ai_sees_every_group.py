"""What the AI is told about a study: every answer, with its unit, and the groups.

"Tulkintojen tekeminen ei onnistu" — on a 41-respondent study split by six
companies, verified 2026-09-17:

* a headline on a slide split by Yritys was written from the WHOLE SAMPLE only:
  with a Total column the findings took Total's top categories and never looked
  at the groups, so it said "toimija" and compared nothing;
* the numbers went out bare ("Delta: 22"), and the demographics bullet read them
  as counts: "63 respondents from three companies" of a 41-respondent study;
* only the top 3–4 answers went out, so the chat named four of six companies and
  could not say which was rated most reliable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from reportbuilder.ai import text as T
from reportbuilder.api import routes_ai as R
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.stats.series import Cell, SeriesResult

pytestmark = pytest.mark.unit

COMPANIES = ["Amazon", "Walmart", "Delta", "Salesforce", "Aramco", "nSight"]


def _split_series() -> SeriesResult:
    cats = ("5", "4", "3", "2", "1")
    segs = tuple(COMPANIES) + ("Total",)
    cells = {(c, s): Cell(pct=float((i * 7 + j * 3) % 60)) for i, c in enumerate(cats)
             for j, s in enumerate(segs)}
    base = dict(zip(COMPANIES, [3, 6, 9, 6, 9, 8])) | {"Total": 41}
    return SeriesResult(categories=cats, segments=segs, cells=cells, base_n=base, statistic="pct")


# ---- units ---------------------------------------------------------------------

def test_a_finding_is_still_a_plain_pair():
    f = R.Finding("Delta", 22.0, "%")
    assert f == ("Delta", 22.0)
    label, value = f
    assert f.unit == "%"


def test_a_share_is_written_with_its_percent_sign():
    block = T._findings_block([("Yritys", [R.Finding("Delta", 22.0, "%")])])
    assert "Delta: 22 %" in block


def test_a_bare_pair_is_written_as_before():
    assert "- Delta: 22" in T._findings_block([("Yritys", [("Delta", 22.0)])])


def test_the_title_prompt_carries_the_unit():
    prompt = T._slide_title_prompt("Yritys", [R.Finding("Delta", 22.0, "%")])
    assert "Delta: 22 %" in prompt


# ---- a split slide tells the model about its groups ------------------------------

def test_a_split_series_gives_each_group_with_its_base():
    groups = R._group_findings(_split_series())
    labels = [label for label, _v in groups]
    for company, n in zip(COMPANIES, [3, 6, 9, 6, 9, 8]):
        assert any(label.startswith(f"{company} (n={n}) — ") for label in labels), labels
    assert all(getattr(g, "unit", "") == "%" for g in groups)


def test_a_series_without_groups_adds_nothing():
    s = SeriesResult(categories=("A",), segments=("Total",), cells={("A", "Total"): Cell(pct=50.0)},
                     base_n={"Total": 10}, statistic="pct")
    assert R._group_findings(s) == []


def test_the_title_prompt_asks_for_a_comparison_when_groups_are_given():
    prompt = T._slide_title_prompt("Luotettava", R._group_findings(_split_series()))
    assert "Amazon (n=3)" in prompt
    assert "ryhmien" in prompt and "10" in prompt


def test_a_prompt_without_groups_says_nothing_about_them():
    prompt = T._slide_title_prompt("Yritys", [("Delta", 22.0)])
    assert "ryhmien" not in prompt


# ---- every answer when there are few ----------------------------------------------

def test_few_answers_are_all_given():
    assert R._answers_to_give(("a",) * 6, top_n=3) == 6
    assert R._answers_to_give(("a",) * 8, top_n=3) == 8


def test_many_answers_are_cut_to_the_top():
    assert R._answers_to_give(("a",) * 20, top_n=3) == 3


def _study():
    rng = np.random.default_rng(1)
    n = 41
    yritys = Variable("Yritys", "Yritys", "categorical",
                      tuple(ValueLabel(float(i + 1), c) for i, c in enumerate(COMPANIES)), frozenset())
    luot = Variable("Luotettava", "Luotettava", "categorical",
                    (ValueLabel(1.0, "1 = Erittäin huonosti"), ValueLabel(5.0, "5 = Erittäin hyvin")),
                    frozenset())
    model = QuestionModel(variables={"Yritys": yritys, "Luotettava": luot}, questions=[
        Question(qid="yritys", kind="single", variables=("Yritys",), text="Yritys"),
        Question(qid="luotettava", kind="single", variables=("Luotettava",), text="Luotettava"),
    ])
    df = pd.DataFrame({"Yritys": np.resize(np.arange(1, 7), n).astype(float),
                       "Luotettava": rng.choice(range(1, 6), n).astype(float)})
    return df, model


def test_every_company_reaches_the_findings():
    df, model = _study()
    findings = dict(R._findings_for_refs(["yritys"], df, model))
    labels = sorted(label for label, _v in findings["Yritys"])
    assert labels == sorted(COMPANIES)
    assert all(getattr(f, "unit", "") == "%" for f in findings["Yritys"])


def test_the_chat_is_given_each_question_by_group(monkeypatch):
    df, model = _study()
    monkeypatch.setattr(R, "_background_classifiers", lambda df, model: ["Yritys"])
    crossed = R._crossed_findings(["luotettava"], df, model)
    assert crossed, "no question was crossed by the classifier"
    title, lines = crossed[0]
    assert "Luotettava" in title and "Yritys" in title
    assert any(label.startswith("Amazon (n=") for label, _v in lines)


def test_the_chat_prompt_contains_the_crossed_data():
    chat = []
    reply = T.generate_data_chat(
        "Testi", [("Yritys", [R.Finding("Delta", 22.0, "%")])], [{"role": "user", "content": "?"}],
        total_n=41, crossed=[("Luotettava — ryhmittäin: Yritys", [R.Finding("Amazon (n=3) — 3", 33.0, "%")])],
        chat=lambda p: chat.append(p) or "ok")
    assert reply == "ok"
    assert "Amazon (n=3) — 3: 33 %" in chat[0]


def test_a_rating_question_is_compared_by_its_mean(monkeypatch):
    """"Which company was rated most reliable?" was answered "nSight, whose most
    common rating was 1 (37 %)" — 1 being the worst end of the scale. A mode on a
    scale carries no direction; a mean does, and the scale is named with it."""
    df, model = _study()
    monkeypatch.setattr(R, "_background_classifiers", lambda df, model: ["Yritys"])
    crossed = R._crossed_findings(["luotettava"], df, model)
    title, lines = crossed[0]
    assert "keskiarvo" in title
    assert all(" — " not in label for label, _v in lines), lines
    assert all(1.0 <= v <= 5.0 for _label, v in lines), lines


def test_a_nominal_question_keeps_its_strongest_answer(monkeypatch):
    df, model = _study()
    monkeypatch.setattr(R, "_background_classifiers", lambda df, model: ["Luotettava"])
    crossed = R._crossed_findings(["yritys"], df, model)
    if crossed:
        title, lines = crossed[0]
        assert "yleisin vastaus" in title
        assert any(" — " in label for label, _v in lines), lines


def test_the_headline_is_told_which_end_of_the_scale_is_good():
    """The findings of a rating question are its scale points ("— 5: 33 %"), and
    5 means nothing without the scale. The chart prints it under itself
    ("1 = Erittäin huonosti · 5 = Erittäin hyvin"); the prompt says it too."""
    prompt = T._slide_title_prompt(
        "Luotettava", [R.Finding("Amazon (n=3) — 5", 33.0, "%")],
        scale="1 = Erittäin huonosti · 5 = Erittäin hyvin")
    assert "1 = Erittäin huonosti · 5 = Erittäin hyvin" in prompt


def test_without_a_scale_the_prompt_is_what_it_was():
    assert "Asteikko" not in T._slide_title_prompt("Yritys", [("Delta", 22.0)])
