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
                          slots={},
                          fonts={"category_names": ("Arial", 10),
                                 "legend": ("Arial", 10),
                                 "n_annotation": ("Arial", 9)},
                          palette=["1F77B4"])
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

    def test_a_partial_area_amends_where_the_chart_ALREADY_goes(self):
        """No slot does not mean no rectangle.

        Where a template offers no usable content area — Arla, whose every
        layout is two-column — the renderer places the chart itself, and that
        placement is what a drag amends. This used to require all four numbers,
        so dragging such a chart, which sends only x and y, changed nothing at
        all: "when content is resizing or moving the chart does not update".
        """
        s = _spec()
        s.chart_slot = None
        apply_template_overrides(s, {"content": {"y": 2.0}})
        assert s.chart_slot is not None
        assert s.chart_slot.top == int(2.0 * EMU_IN)
        # The edges nobody touched keep the placement they had.
        assert s.chart_slot.width > 0 and s.chart_slot.height > 0


class TestChartText:
    """"Content font and size" means the chart's own text — the row labels down
    the side, the numbers in the bars, the legend, the axis. The first thing
    anyone asked for after seeing a rendered slide was labels that fit."""

    # Asserted through `font_for`, which is what the renderers call. Asserting
    # on a `fonts` attribute passed while production was untouched: the override
    # was writing one the constructor never made and nothing reads.

    def test_the_size_reaches_the_row_labels(self):
        s = _spec()
        apply_template_overrides(s, {"content": {"size": 8}})
        assert s.font_for("category_names") == ("Arial", 8)
        assert s.font_for("legend") == ("Arial", 8)

    def test_the_family_reaches_them_too_and_keeps_the_size(self):
        s = _spec()
        apply_template_overrides(s, {"content": {"font": "Verdana"}})
        assert s.font_for("category_names") == ("Verdana", 10)
        assert s.body_font == "Verdana"

    def test_saying_nothing_leaves_the_chart_alone(self):
        s = _spec()
        apply_template_overrides(s, {"content": {"x": 1.0}})
        assert s.font_for("category_names") == ("Arial", 10)


class TestDerivedElements:
    """The subtitle and the footer have no box of their own.

    The subtitle sits a fixed gap above the chart, bottom-anchored, sharing the
    title's left and width; the footer sits a fixed gap above the template's own
    foot. So there is nothing to move — but their SIZE is the first thing an
    author reaches for. The complaint that started this asked for exactly that:
    "kysymystekstin (subtitle) pienentäminen", shrinking a question too long for
    its line.
    """

    def test_the_subtitle_can_be_shrunk(self):
        s = _spec()
        apply_template_overrides(s, {"subtitle": {"size": 10, "font": "Verdana"}})
        assert s.subtitle_size_pt == 10
        assert s.subtitle_font == "Verdana"

    def test_the_subtitle_can_be_recoloured(self):
        s = _spec()
        apply_template_overrides(s, {"subtitle": {"colour": "#666666"}})
        assert s.subtitle_colour == "666666"

    def test_the_footer_is_a_font_role_like_any_other(self):
        """"n = 3144" is drawn from `n_annotation`, so its size goes where every
        other chart-text size goes rather than into a special case."""
        s = _spec()
        apply_template_overrides(s, {"footer": {"size": 11}})
        assert s.font_for("n_annotation") == ("Arial", 11)

    def test_saying_nothing_about_them_changes_nothing(self):
        s = _spec()
        apply_template_overrides(s, {"title": {"colour": "FFFFFF"}})
        assert s.subtitle_size_pt == 0.0 and s.subtitle_font == ""
        assert s.font_for("n_annotation") == ("Arial", 9)

    def test_a_stale_resolved_spec_is_dropped(self):
        """It was built from the sizes as they were; anything reading it would
        go on answering with those."""
        s = _spec()
        s.resolved_spec = object()
        apply_template_overrides(s, {"content": {"size": 8}})
        assert s.resolved_spec is None


class TestTheTitleSizeReachesTheRenderer:
    """The drawn title takes its size from the `title` font role, which
    `build_spec` reads — not from the harvested profile. Setting only the
    profile stored the number, echoed it back in the editor, and left the
    headline exactly as it was on every template whose title is drawn rather
    than inherited from a placeholder."""

    def test_the_size_lands_in_the_font_role(self):
        s = _spec()
        apply_template_overrides(s, {"title": {"size": 24}})
        assert s.font_for("title")[1] == 24

    def test_the_family_lands_there_too(self):
        s = _spec()
        apply_template_overrides(s, {"title": {"font": "Georgia"}})
        assert s.font_for("title")[0] == "Georgia"

    def test_and_still_on_the_profile_where_the_box_is_measured(self):
        class _T:
            font = ""; size_pt = 0.0; left = 0; top = 0; width = 0; height = 0
        class _P:
            title = _T()
        s = _spec()
        s.profile = _P()
        apply_template_overrides(s, {"title": {"size": 24}})
        assert s.profile.title.size_pt == 24
