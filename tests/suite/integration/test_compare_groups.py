"""A generated comparison slide must render as a real two-group chart.
(spec 2026-08-02-compare-groups-section §5)"""
from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

from reportbuilder.api.model_loader import df_model_for_material
from reportbuilder.model.report import report_from_json
from reportbuilder.stats import engine
from reportbuilder.store.memory_client import InMemoryDataHiveClient

_STORE = pathlib.Path("work/demo-store")


def _load():
    if not (_STORE / "materials" / "mat-erisan.sav").exists():
        pytest.skip("mat-erisan not available locally")
    rep = json.loads(json.loads((_STORE / "reports.json").read_text())["rep-erisan"])
    r = report_from_json(rep)
    df, model = df_model_for_material(
        "mat-erisan", InMemoryDataHiveClient(storage_dir=str(_STORE)), rep["grouping"])
    return r, df, model


def _a_single_chart(r, model):
    """The first ordinary single-question chart in the report.

    Chosen dynamically rather than by qid: the fixture report is edited by hand
    during testing, so pinning "var3" made these tests fail the moment that slide
    was removed."""
    for c in r.charts:
        if c.chart_type.startswith("special") or c.compare_group:
            continue
        try:
            q = model.question(c.question_ref)
        except Exception:
            continue
        if q.kind == "single" and 2 <= len(model.variables[q.variables[0]].value_labels) <= 8:
            return c, q
    pytest.skip("no suitable single-question chart in the fixture report")


def _generated(src, classifying_var="polku"):
    """What makeComparisonSlide produces, mirrored in Python."""
    return dataclasses.replace(
        src,
        classifying_var=classifying_var,
        classifying_var_2=None,
        compare_group=classifying_var,
        percent_base="auto",
        slide_title=None,
        chart_type=("horizontal_bar"
                    if src.chart_type in ("pie", "doughnut", "funnel",
                                          "wordcloud", "themes")
                    else src.chart_type),
    )


def test_a_generated_slide_has_two_groups_with_the_known_bases():
    r, df, model = _load()
    src, q = _a_single_chart(r, model)
    res = engine.compute(q, _generated(src), df, model)
    assert sorted(res.base_n[s] for s in res.segments if s != "Total") == [255, 256]


def test_a_pie_becomes_a_bar_so_both_groups_are_visible():
    """The customer's total-level slide is a pie; a pie cannot draw two series."""
    r, df, model = _load()
    src, _q = _a_single_chart(r, model)
    pie = dataclasses.replace(src, chart_type="pie")
    assert _generated(pie).chart_type == "horizontal_bar"
    # a chart type that CAN show two series is left alone
    assert _generated(dataclasses.replace(src, chart_type="horizontal_bar")).chart_type \
        == "horizontal_bar"
    assert _generated(
        dataclasses.replace(src, chart_type="stacked_horizontal_bar")
    ).chart_type == "stacked_horizontal_bar"


def test_clearing_the_second_classifier_avoids_the_banner_error():
    """A source slide that is a cross-tab would otherwise raise: the engine rejects
    a banner classifier combined with a second classifying variable."""
    r, df, model = _load()
    src, q = _a_single_chart(r, model)
    crossed = dataclasses.replace(src, classifying_var="var5", classifying_var_2="var6")
    engine.compute(q, _generated(crossed), df, model)  # must not raise


def test_carrying_the_second_classifier_over_would_have_raised():
    """Pins WHY the field is cleared, so a future refactor cannot quietly undo it."""
    r, df, model = _load()
    src, q = _a_single_chart(r, model)
    bad = dataclasses.replace(src, classifying_var="polku", classifying_var_2="var5")
    with pytest.raises(ValueError, match="second classifying variable"):
        engine.compute(q, bad, df, model)


def test_a_generated_slide_carries_no_title():
    """So a dozen generated slides fire no AI title calls."""
    r, _df, model = _load()
    src, _q = _a_single_chart(r, model)
    assert _generated(dataclasses.replace(src, slide_title="X")).slide_title is None


def test_both_encodings_of_the_path_generate_the_same_numbers():
    r, df, model = _load()
    src, q = _a_single_chart(r, model)
    by_banner = engine.compute(q, _generated(src, "polku"), df, model)
    by_string = engine.compute(q, _generated(src, "var214"), df, model)
    assert sorted(by_banner.base_n[s] for s in by_banner.segments if s != "Total") == \
           sorted(by_string.base_n[s] for s in by_string.segments if s != "Total")
