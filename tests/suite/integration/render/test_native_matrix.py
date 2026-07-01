"""Native-render matrix: native-capable types add a real c:chart graphicFrame
(not a picture); combo/wordcloud raise NativeUnsupportedError; and the shared
series_chart_data helper yields the expected categories + one series per segment.
"""
from __future__ import annotations

import pytest

from suite._helpers import make_ctx, picture_shapes
from suite.integration.render._series import series_for, multiseg_series

from reportbuilder.render.native import NATIVE_BUILDERS, NativeUnsupportedError
from reportbuilder.render.native.column import series_chart_data

# All types except combo/wordcloud have a native OOXML form.
NATIVE_TYPES = [
    "vertical_bar", "horizontal_bar", "stacked_vertical_bar", "stacked_horizontal_bar",
    "line", "pie", "doughnut", "radar", "scatter", "funnel",
]
UNSUPPORTED_TYPES = ["combo", "wordcloud"]


def test_registry_has_all_twelve():
    assert set(NATIVE_BUILDERS) == set(NATIVE_TYPES) | set(UNSUPPORTED_TYPES)
    assert len(NATIVE_BUILDERS) == 12


@pytest.mark.parametrize("chart_type", NATIVE_TYPES)
def test_native_builder_adds_chart_not_picture(chart_type):
    """Builder returns a graphicFrame carrying a c:chart, and no PICTURE appears."""
    series, overrides = series_for(chart_type)
    prs, slide, slot, ctx = make_ctx(chart_type, series, **overrides)

    gf = NATIVE_BUILDERS[chart_type](ctx)

    assert gf.has_chart, f"{chart_type} native builder should return a chart graphicFrame"
    # A real c:chart element must be present on the returned frame.
    assert gf.chart is not None
    # Native charts are NOT pictures.
    assert len(picture_shapes(slide)) == 0
    # And the chart shape is discoverable on the slide.
    assert any(getattr(sh, "has_chart", False) for sh in slide.shapes)


@pytest.mark.parametrize("chart_type", UNSUPPORTED_TYPES)
def test_native_unsupported_raises(chart_type):
    """combo and wordcloud have no native form -> NativeUnsupportedError."""
    series, overrides = series_for(chart_type)
    prs, slide, slot, ctx = make_ctx(chart_type, series, **overrides)
    with pytest.raises(NativeUnsupportedError):
        NATIVE_BUILDERS[chart_type](ctx)


def test_series_chart_data_shape():
    """series_chart_data(series, 'pct') -> categories match, one series per segment."""
    series = multiseg_series(("A", "B", "C", "D"), ("G1", "G2"))
    cd = series_chart_data(series, "pct")

    cat_labels = [c.label for c in cd.categories]
    assert cat_labels == list(series.categories)

    # One CategoryChartData series per SeriesResult segment, named by segment.
    assert len(cd._series) == len(series.segments)
    assert [s.name for s in cd._series] == list(series.segments)

    # Values line up with the source cells for the first segment.
    expected = [series.cell(c, "G1").value("pct") for c in series.categories]
    assert list(cd._series[0].values) == expected
