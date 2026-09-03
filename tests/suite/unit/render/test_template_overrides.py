"""An author's corrections to what we harvested from their template.

Harvesting is a guess made from a file nobody wrote for us, and on the evidence
of three customer templates it is wrong in different ways each time: Arla's
title colour was discarded, its every layout is two-column, Prima Pet's
representative slide carries a 2.61in title box. The automatic rules are better
now, but the next template will find a new way to be unusual — so an author can
say what the answer is, per template, and be believed.

Blank means inherit. A template nobody has touched renders exactly as the
harvester decided, which is what keeps this an override rather than a
requirement.
"""
from __future__ import annotations

from reportbuilder.render.style_spec import apply_template_overrides
from reportbuilder.render.base import Slot
from reportbuilder.render.style_spec import TemplateStyleSpec

EMU_IN = 914400


def _spec():
    s = TemplateStyleSpec(slide_width=int(13.333 * EMU_IN), slide_height=int(7.5 * EMU_IN),
                          slots={}, fonts={}, palette=["1F77B4"])
    s.ink, s.background, s.accent = "000000", "FFFFFF", "82CE71"
    s.chart_slot = Slot(slide_index=-1, left=EMU_IN, top=EMU_IN,
                        width=6 * EMU_IN, height=3 * EMU_IN, name="chart")
    return s


class TestNothingToSay:
    def test_no_overrides_changes_nothing(self):
        s = _spec()
        apply_template_overrides(s, {})
        assert (s.ink, s.background, s.accent) == ("000000", "FFFFFF", "82CE71")
        assert s.chart_slot.width == 6 * EMU_IN

    def test_blank_values_are_not_overrides(self):
        """An emptied field means "inherit", not "set it to nothing"."""
        s = _spec()
        apply_template_overrides(s, {"title": {"colour": "", "font": ""},
                                     "accent": "", "background": ""})
        assert (s.ink, s.background, s.accent) == ("000000", "FFFFFF", "82CE71")


class TestColours:
    def test_the_title_colour_can_be_set(self):
        """The Arla case, said by hand: a white title on a black band."""
        s = _spec()
        apply_template_overrides(s, {"title": {"colour": "FFFFFF"}})
        assert s.ink == "FFFFFF"

    def test_a_leading_hash_is_accepted(self):
        s = _spec()
        apply_template_overrides(s, {"title": {"colour": "#FFFFFF"}})
        assert s.ink == "FFFFFF"

    def test_accent_and_background(self):
        s = _spec()
        apply_template_overrides(s, {"accent": "FF5000", "background": "F7F3EC"})
        assert (s.accent, s.background) == ("FF5000", "F7F3EC")


class TestGeometry:
    def test_the_content_area_can_be_moved_and_resized(self):
        """Given in inches, because that is what a ruler in PowerPoint says."""
        s = _spec()
        apply_template_overrides(s, {"content": {"x": 0.5, "y": 1.75,
                                                 "w": 12.33, "h": 5.0}})
        assert s.chart_slot.left == int(0.5 * EMU_IN)
        assert s.chart_slot.top == int(1.75 * EMU_IN)
        assert s.chart_slot.width == int(12.33 * EMU_IN)
        assert s.chart_slot.height == int(5.0 * EMU_IN)

    def test_one_edge_at_a_time(self):
        """Nudging the top must not silently reset the other three."""
        s = _spec()
        apply_template_overrides(s, {"content": {"y": 2.0}})
        assert s.chart_slot.top == int(2.0 * EMU_IN)
        assert s.chart_slot.left == EMU_IN
        assert s.chart_slot.width == 6 * EMU_IN

    def test_a_content_area_can_be_given_where_there_was_none(self):
        """Arla has no usable content box, so we place the chart ourselves —
        until an author says where it goes."""
        s = _spec()
        s.chart_slot = None
        apply_template_overrides(s, {"content": {"x": 0.66, "y": 2.0,
                                                 "w": 12.0, "h": 4.5}})
        assert s.chart_slot is not None
        assert s.chart_slot.width == int(12.0 * EMU_IN)

    def test_a_half_given_area_is_ignored(self):
        """Three numbers do not make a box, and guessing the fourth would put a
        chart somewhere nobody asked for."""
        s = _spec()
        s.chart_slot = None
        apply_template_overrides(s, {"content": {"x": 0.66, "y": 2.0, "w": 12.0}})
        assert s.chart_slot is None


class TestChartText:
    """"Content font and size" means the chart's own text — the row labels down
    the side, the numbers in the bars, the legend, the axis. The first thing
    anyone asked for after seeing a rendered slide was labels that fit."""

    def test_the_size_reaches_the_row_labels(self):
        s = _spec()
        s.fonts = {"category_names": ("Arial", 10), "legend": ("Arial", 10)}
        apply_template_overrides(s, {"content": {"size": 8}})
        assert s.fonts["category_names"] == ("Arial", 8)
        assert s.fonts["legend"] == ("Arial", 8)

    def test_the_family_reaches_them_too_and_keeps_the_size(self):
        s = _spec()
        s.fonts = {"category_names": ("Arial", 10)}
        apply_template_overrides(s, {"content": {"font": "Verdana"}})
        assert s.fonts["category_names"] == ("Verdana", 10)
        assert s.body_font == "Verdana"

    def test_saying_nothing_leaves_the_chart_alone(self):
        s = _spec()
        s.fonts = {"category_names": ("Arial", 10)}
        apply_template_overrides(s, {"content": {"x": 1.0}})
        assert s.fonts["category_names"] == ("Arial", 10)
