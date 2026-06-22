"""Tests for shared test fixture builders (Task 0.10 / plan §C7)."""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import QuestionModel
from reportbuilder.model.report import Report
from reportbuilder.testing.fixtures import (
    known_pcts,
    known_series,
    one_chart_report,
    report_json_n_charts,
    synthetic_sav,
    synthetic_sav_bytes,
    tiny_model_and_data,
    tiny_question_model,
    two_chart_report,
)


def test_tiny_question_model_type():
    qm = tiny_question_model()
    assert isinstance(qm, QuestionModel)


def test_tiny_question_model_has_q1():
    qm = tiny_question_model()
    q = qm.question("q1")
    assert q.qid == "q1"


def test_tiny_model_and_data_types():
    qm, df = tiny_model_and_data()
    assert isinstance(qm, QuestionModel)
    assert isinstance(df, pd.DataFrame)


def test_tiny_model_and_data_shape():
    _, df = tiny_model_and_data()
    assert len(df) == 5
    assert "q1" in df.columns


def test_known_pcts_values():
    assert known_pcts() == [60.0, 40.0]


def test_known_series_matches_known_pcts():
    series = known_series()
    pcts = known_pcts()
    assert series.cell("Yes", "Total").pct == pcts[0]
    assert series.cell("No", "Total").pct == pcts[1]


def test_known_series_yes_pct():
    assert known_series().cell("Yes", "Total").pct == 60.0


def test_one_chart_report_type():
    assert isinstance(one_chart_report(), Report)


def test_one_chart_report_render_mode():
    assert one_chart_report().render_mode == "native"


def test_one_chart_report_chart_count():
    assert len(one_chart_report().charts) == 1


def test_two_chart_report_chart_count():
    assert len(two_chart_report().charts) == 2


def test_report_json_n_charts_is_dict():
    result = report_json_n_charts(3)
    assert isinstance(result, dict)


def test_report_json_n_charts_count():
    result = report_json_n_charts(3)
    assert len(result["charts"]) == 3


def test_synthetic_sav_exists(tmp_path):
    path = synthetic_sav(tmp_path)
    from pathlib import Path
    p = Path(path)
    assert p.exists()
    assert p.stat().st_size > 0


def test_synthetic_sav_bytes_is_bytes():
    data = synthetic_sav_bytes()
    assert isinstance(data, bytes)


def test_synthetic_sav_bytes_nonempty():
    data = synthetic_sav_bytes()
    assert len(data) > 0
