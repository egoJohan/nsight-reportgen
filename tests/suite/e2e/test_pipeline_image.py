"""SOFFICE-FREE full data→render pipeline over the synthetic SAV.

Drives the real ingest → enrich → compute → image-builder chain and asserts that
every core chart type emits exactly one undistorted PICTURE shape. No LibreOffice
is involved (image builders rasterise via matplotlib), so this runs everywhere.

Flow per chart type: read_sav(synthetic) → enrich_model → compute(series) →
IMAGE_BUILDERS[type](ctx) → assert_single_picture.
"""
from __future__ import annotations

import pytest

from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.stats.engine import compute
from reportbuilder.testing.fixtures import synthetic_sav

from suite._helpers import assert_single_picture, make_ctx, make_spec


@pytest.fixture
def model_and_data(tmp_path):
    """(df, enriched model) from the synthetic SAV — the standard pipeline input."""
    df, model = read_sav(synthetic_sav(tmp_path))
    return df, enrich_model(model)


@pytest.mark.parametrize("chart_type", ["vertical_bar", "horizontal_bar", "line", "pie"])
def test_single_choice_renders_one_picture(chart_type, model_and_data):
    """q1 (single Yes/No) → compute → image build → exactly one PICTURE."""
    df, model = model_and_data
    question = model.question("q1")
    spec = make_spec(chart_type, question_ref="q1")
    series = compute(question, spec, df, model)

    _prs, slide, slot, ctx = make_ctx(chart_type, series, question_ref="q1")
    IMAGE_BUILDERS[chart_type](ctx)

    assert_single_picture(slide, slot)


def test_multi_question_renders_one_picture(model_and_data):
    """The auto-grouped multi question (m1+m2) renders a single PICTURE."""
    df, model = model_and_data
    multi = next(q for q in model.questions if q.kind == "multi")
    assert set(multi.variables) == {"m1", "m2"}

    spec = make_spec("vertical_bar", question_ref=multi.qid)
    series = compute(multi, spec, df, model)

    _prs, slide, slot, ctx = make_ctx("vertical_bar", series, question_ref=multi.qid)
    IMAGE_BUILDERS["vertical_bar"](ctx)

    assert_single_picture(slide, slot)


def test_stacked_with_classifying_var_renders_one_picture(model_and_data):
    """A stacked chart: q1 classified by m1 (a second categorical) → one PICTURE.

    The classifier splits q1 into per-segment stacks; the series carries multiple
    segments, and the stacked builder still emits exactly one undistorted PNG.
    """
    df, model = model_and_data
    question = model.question("q1")
    spec = make_spec("stacked_vertical_bar", question_ref="q1", classifying_var="m1")
    series = compute(question, spec, df, model)
    # The classifier produced real segments (not just a Total column).
    assert len(series.segments) > 1

    _prs, slide, slot, ctx = make_ctx(
        "stacked_vertical_bar", series, question_ref="q1", classifying_var="m1"
    )
    IMAGE_BUILDERS["stacked_vertical_bar"](ctx)

    assert_single_picture(slide, slot)
