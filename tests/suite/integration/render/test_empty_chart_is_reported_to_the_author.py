"""The deck builder says which charts had nothing to plot.

The placeholder used to say "No data to show" on the slide itself. Now it says
nothing (see test_empty_chart_says_nothing_on_the_slide), which leaves the
author with no way to notice — so the builder reports it instead, and the
preview endpoint turns that into the `X-Chart-Empty` header the editor raises as
a slide problem.

It is reported from where the series is COMPUTED, using the same
`series_is_empty` the renderer branches on, so the two cannot disagree about
which slide is blank. (Johan, 2026-09-16)
"""
from __future__ import annotations

import dataclasses

import pytest

from reportbuilder.export.pptx_build import build_presentation, build_pptx
from reportbuilder.testing.fixtures import one_chart_report, tiny_model_and_data

pytestmark = pytest.mark.integration


def _image_report():
    return dataclasses.replace(one_chart_report(), render_mode="image")


def test_a_chart_with_nothing_to_plot_is_named():
    model, df = tiny_model_and_data()
    blank = df.assign(q1=[float("nan")] * len(df))
    empty: list[str] = []
    build_presentation(_image_report(), model, blank, empty_out=empty)
    assert empty == ["q1"]


def test_a_chart_with_data_is_not_named():
    model, df = tiny_model_and_data()
    empty: list[str] = []
    build_presentation(_image_report(), model, df, empty_out=empty)
    assert empty == []


def test_the_file_builder_reports_it_too(tmp_path):
    """Both endings of the same build. The preview takes the fast path when it
    draws the title itself and LibreOffice when it does not, and an author
    warned on one and not the other would be the WYSIWYG gap this pipeline
    exists to close."""
    model, df = tiny_model_and_data()
    blank = df.assign(q1=[float("nan")] * len(df))
    empty: list[str] = []
    build_pptx(_image_report(), model, blank, str(tmp_path / "d.pptx"),
               empty_out=empty)
    assert empty == ["q1"]
