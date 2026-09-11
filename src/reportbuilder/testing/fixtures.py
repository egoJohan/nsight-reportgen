"""Shared test fixture builders for reportbuilder tests (plan §C7 / Task 0.10)."""
from __future__ import annotations
import json
import tempfile
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
import pyreadstat
from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.model.report import (
    Report, ChartSpec, SortSpec, NumberFormat, ElementToggles, report_to_json,
)
from reportbuilder.stats.series import Cell, SeriesResult

# ---------------------------------------------------------------------------
# Golden bindings for the Attendo aided-awareness question.
# Copied VERBATIM from src/nsight/attendo_bindings.py (Task 1.4).
# Do NOT import that module — these are data constants for reportbuilder tests.
# ---------------------------------------------------------------------------

# brand -> SPSS variable name (var18 grid, one checkbox per brand).
ATTENDO_AIDED_VARS: dict[str, str] = {
    "Attendo": "var18O45",
    "Esperi": "var18O46",
    "Rinnekodit": "var18O51",
    "Validia": "var18O52",
    "Onnikodit": "var18O48",
    "Mainio-kodit": "var18O47",
    "Ykköskodit": "var18O49",
    "Humana": "var18O50",
    "En mitään näistä": "var18O53",
}

# Deck ground truth (slide idx 14, series "Marraskuu 2025"), as whole percents.
DECK_AIDED_AWARENESS: dict[str, int] = {
    "Attendo": 86,
    "Esperi": 75,
    "Rinnekodit": 42,
    "Validia": 33,
    "Onnikodit": 26,
    "Mainio-kodit": 22,
    "Ykköskodit": 15,
    "Humana": 13,
    "En mitään näistä": 5,
}


# ---------------------------------------------------------------------------
# Golden bindings for the Attendo general-opinion question (M-2).
# Copied VERBATIM from src/nsight/attendo_bindings.py (Task 3.7).
# Do NOT import that module — these are data constants for reportbuilder tests.
# ---------------------------------------------------------------------------

# SPSS variable names for private/public opinion questions (slide idx 17).
OPINION_PRIVATE_VAR: str = "var20"
OPINION_PUBLIC_VAR: str = "var21"

# Chart series label -> SPSS code mapping.
OPINION_SERIES_CODES: dict[str, float] = {
    "Erittäin huono": 10054.0,
    "Huono": 10055.0,
    "Hyvä": 10056.0,
    "Erittäin hyvä": 10057.0,
    "En osaa sanoa": 10058.0,
}

# Deck chart series proportions (slide idx 17, current wave).
DECK_OPINION_DIST: dict[str, dict[str, float]] = {
    "private": {"Erittäin huono": 0.05, "Huono": 0.26, "Hyvä": 0.47,
                "Erittäin hyvä": 0.10, "En osaa sanoa": 0.12},
    "public": {"Erittäin huono": 0.06, "Huono": 0.26, "Hyvä": 0.51,
               "Erittäin hyvä": 0.07, "En osaa sanoa": 0.10},
}

# Deck positive % shown in TextBox (slide idx 17): Hyvä + Erittäin hyvä.
DECK_OPINION_POSITIVE: dict[str, int] = {"private": 58, "public": 58}


def aided_question(model: QuestionModel) -> tuple[QuestionModel, Question]:
    """Build the aided-awareness multi question with brand-named member labels.
    Returns (model2, question). (golden bindings copied from nsight/attendo_bindings.py)"""
    new_vars = dict(model.variables)
    members = []
    for brand, varname in ATTENDO_AIDED_VARS.items():
        new_vars[varname] = replace(model.variables[varname], label=brand)
        members.append(varname)
    model2 = QuestionModel(variables=new_vars, questions=[])
    q = Question(qid="aided", kind="multi", variables=tuple(members), text="Aided awareness")
    return model2, q


def tiny_question_model() -> QuestionModel:
    q1 = Variable(name="q1", label="Satisfaction", measurement="categorical",
                  value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
                  missing_values=frozenset())
    age = Variable(name="age", label="Age", measurement="scale",
                   value_labels=(), missing_values=frozenset())
    questions = [
        Question(qid="q1", kind="single", variables=("q1",), text="Satisfaction"),
        Question(qid="age", kind="single", variables=("age",), text="Age"),
    ]
    return QuestionModel(variables={"q1": q1, "age": age}, questions=questions)


def tiny_model_and_data() -> tuple[QuestionModel, pd.DataFrame]:
    df = pd.DataFrame({"q1": [1.0, 1.0, 1.0, 2.0, 2.0], "age": [30.0, 40.0, 50.0, 60.0, 70.0]})
    return tiny_question_model(), df


def known_series() -> SeriesResult:
    return SeriesResult(
        categories=("Yes", "No"), segments=("Total",),
        cells={("Yes", "Total"): Cell(pct=60.0, count=3.0, mean=None),
               ("No", "Total"): Cell(pct=40.0, count=2.0, mean=None)},
        base_n={"Total": 5}, statistic="pct",
    )


def known_pcts() -> list[float]:
    return [60.0, 40.0]


def _chart(question_ref: str = "q1", chart_type: str = "vertical_bar", slot: str = "slot1") -> ChartSpec:
    return ChartSpec(
        question_ref=question_ref, chart_type=chart_type, statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot=slot, elements=ElementToggles(),
    )


def one_chart_report() -> Report:
    return Report(name="R1", render_mode="native", template_ref="t.pptx", charts=(_chart(),))


def two_chart_report() -> Report:
    return Report(name="R2", render_mode="native", template_ref="t.pptx",
                  charts=(_chart(slot="slot1"), _chart(slot="slot2")))


def report_json_n_charts(n: int) -> dict:
    charts = tuple(_chart(slot=f"slot{i + 1}") for i in range(n))
    report = Report(name=f"R-{n}", render_mode="native", template_ref="t.pptx", charts=charts)
    return json.loads(report_to_json(report))


def synthetic_sav(tmp_path) -> str:
    df = pd.DataFrame({
        "q1": [1.0, 1.0, 1.0, 2.0, 2.0],
        "m1": [1.0, 0.0, 1.0, 0.0, 1.0],
        "m2": [0.0, 1.0, 1.0, 0.0, 0.0],
        "age": [30.0, 40.0, 50.0, 60.0, 70.0],
    })
    path = Path(tmp_path) / "synthetic.sav"
    pyreadstat.write_sav(
        df, str(path),
        column_labels={"q1": "Satisfaction", "m1": "Channel A", "m2": "Channel B", "age": "Age"},
        variable_value_labels={
            "q1": {1: "Yes", 2: "No"},
            "m1": {0: "Unchecked", 1: "Checked"},
            "m2": {0: "Unchecked", 1: "Checked"},
        },
        variable_measure={"q1": "nominal", "m1": "nominal", "m2": "nominal", "age": "scale"},
    )
    return str(path)


def unlabelled_tickbox_sav(tmp_path) -> str:
    """A SAV shaped like the Kaiutinboksi study: a multi-response set whose
    export wrote NO value labels, a tick stored as 1 and a non-tick left blank.

    Its variables were invisible to the grouping editor because every
    groupability test read value labels. Kept as a fixture because "the
    platform wrote no labels" is a shape real files arrive in, not a one-off.
    (Johan, 2026-09-11)
    """
    df = pd.DataFrame({
        # Ticked or blank -- 222 of the study's variables look like this.
        "Hyvatarjous":    [1.0, np.nan, 1.0, np.nan, 1.0],
        "Myyjansuositus": [np.nan, 1.0, 1.0, np.nan, np.nan],
        # A clean 0/1 -- 19 of them look like this.
        "Akt_IPTV":       [0.0, 1.0, 1.0, 0.0, 1.0],
        # Neither: a single-choice 1/2 and a continuous measure, both unlabelled.
        "Gender":         [1.0, 2.0, 1.0, 2.0, 1.0],
        "Age":            [41.0, 63.0, 22.0, 35.0, 58.0],
    })
    path = Path(tmp_path) / "unlabelled.sav"
    pyreadstat.write_sav(
        df, str(path),
        # The tick-boxes carry the OPTION as their label, which is what makes
        # them questions at all -- an unlabelled column whose label is its own
        # name is an analyst working column and stays out of the browser.
        # Gender/Age carry none, exactly as in the customer's file.
        column_labels={"Hyvatarjous": "Hyva tarjous",
                       "Myyjansuositus": "Myyjan suositus",
                       "Akt_IPTV": "Akt IPTV",
                       "Gender": "Gender", "Age": "Age"},
        variable_measure={"Hyvatarjous": "nominal", "Myyjansuositus": "nominal",
                          "Akt_IPTV": "nominal", "Gender": "nominal",
                          "Age": "scale"},
    )
    return str(path)


def unlabelled_tickbox_sav_bytes() -> bytes:
    with tempfile.TemporaryDirectory() as d:
        return Path(unlabelled_tickbox_sav(d)).read_bytes()


def synthetic_sav_bytes() -> bytes:
    with tempfile.TemporaryDirectory() as d:
        return Path(synthetic_sav(d)).read_bytes()
