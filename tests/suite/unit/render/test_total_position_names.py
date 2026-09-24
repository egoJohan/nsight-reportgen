""""Total position" names the places the chart actually has.

"Kun valitsee kaavioksi Stacked Horizontal Bar, kohdassa 'Total position'
puhutaan vertikaaleista kun pitäisi puhua horisontaaleista kun käytetään
luokittelevaa muuttujaa." (2026-09-24)

One list served every chart — "Top (left on vertical charts)", "Bottom (right on
vertical charts)" — so a horizontal bar talked about vertical ones. Each chart
now names its own: a bar's rows are top and bottom, a column chart's columns
left and right, a line's or a radar's series first and last. The stored values
stay "top" and "bottom", so no saved slide moves.
"""
from __future__ import annotations

import pytest

import reportbuilder.render.charts  # noqa: F401 — registers every chart type
from reportbuilder.render.plugins import plugin as get_chart_type

pytestmark = pytest.mark.unit

EXPECTED = {
    "horizontal_bar": ("Top", "Bottom"),
    "stacked_horizontal_bar": ("Top", "Bottom"),
    "vertical_bar": ("Left", "Right"),
    "stacked_vertical_bar": ("Left", "Right"),
    "line": ("First", "Last"),
    "radar": ("First", "Last"),
}


@pytest.mark.parametrize("chart_type,names", EXPECTED.items())
def test_each_chart_names_its_own_places(chart_type, names):
    field = next(f for f in get_chart_type(chart_type).config_schema
                 if f.key == "total_position")
    options = dict(field.options)
    assert (options["top"], options["bottom"]) == names
    assert options["auto"] == "Default"


@pytest.mark.parametrize("chart_type", EXPECTED)
def test_no_chart_talks_about_another(chart_type):
    field = next(f for f in get_chart_type(chart_type).config_schema
                 if f.key == "total_position")
    assert not any("vertical" in label.lower() or "horizontal" in label.lower()
                   for _v, label in field.options)
