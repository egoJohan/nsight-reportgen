"""Harvesting the borrowable part of a customer's template.

Johan's spec: take the title's style and position, the subtitle font, the
graphics belonging to the title and the furniture that repeats on every slide —
then let nSight draw its own slide with those.

Like test_template_check, these run against the real client decks in input/. A
harvester that only works on a template we built ourselves is worthless: the
whole difficulty is that Attendo keeps its brand in its LAYOUTS while Synsam
draws its slides by hand, and only real files show that.
"""
import pathlib

import pytest

from reportbuilder.render.template_profile import extract_profile

_TEMPLATES = {
    "attendo": "input/Attendo Bränditutkimus Marraskuu 2025.pptx",
    "synsam": "input/Synsam_Segmentointitutkimus_30.4.2025_nSight.pptx",
    "holidayclub": "input/Holiday Club_Loyalty tutkimus_raportti_19.2.2026.pptx",
    # Not in git (work/ is ignored): the deck nSight itself produced on stock
    # Office masters. Skipped when absent.
    "agent_deck": "work/attendo_agent_deck.pptx",
}


def _profile(name):
    p = pathlib.Path(_TEMPLATES[name])
    if not p.exists():
        pytest.skip(f"{p} not available locally")
    return extract_profile(str(p))


def _inches(emu):
    return round(emu / 914400, 2)


class TestWhereTheDesignLives:
    """The template itself says whether its design is in the layouts or on its
    slides — by which layout its own slides are built on."""

    @pytest.mark.parametrize("name,layout", [
        ("attendo", "1 layout area"),
        ("holidayclub", "Title and Content"),
    ])
    def test_a_layout_template_is_harvested_from_its_content_layout(self, name, layout):
        """42 of Attendo's 56 slides sit on "1 layout area", and 59 of Holiday
        Club's 123 on "Title and Content". Ranking by decoration instead chose
        Attendo's "Agenda slide" — pretty, but not what the deck is made of."""
        profile = _profile(name)
        assert profile.source == f"layout:{layout}"
        assert profile.layout_index is not None

    @pytest.mark.parametrize("name", ["synsam", "agent_deck"])
    def test_a_hand_drawn_deck_is_harvested_from_a_slide(self, name):
        """Synsam puts 98 of 147 slides on "Tom" and the agent deck all 20 on
        `Blank`. A blank layout cannot hold a chart and a headline, which is
        exactly the signal that the design was drawn on the slides."""
        profile = _profile(name)
        assert profile.source.startswith("slide:")
        assert profile.layout_index is None

    def test_a_section_or_photo_page_is_not_representative(self):
        """Synsam's most common shape count deck-wide belongs to its full-bleed
        photo pages, whose title sits 5.8in down the slide. Body slides only."""
        title = _profile("synsam").title
        assert _inches(title.top) < 1.0


class TestTitleStyle:
    """A layout states almost nothing about its title: it says `+mj-lt` and
    `tx1` and leaves the rest to the master and the theme. Reading only the run
    properties came back empty on all four real templates."""

    @pytest.mark.parametrize("name,font,size", [
        ("attendo", "Century Gothic", 28.0),
        ("holidayclub", "Neue Haas Grotesk Text Pro", 32.0),
        ("synsam", "Avenir Next LT Pro Demi", 22.0),
    ])
    def test_the_title_font_is_resolved_through_what_it_inherits(self, name, font, size):
        profile = _profile(name)
        assert profile.title.font == font
        assert profile.title.size_pt == size

    def test_the_title_colour_is_resolved_through_the_theme(self):
        """`tx1` is a reference, not a colour; the master's colour map and the
        theme's scheme turn it into something we can draw with."""
        assert _profile("holidayclub").title.colour == "131313"

    @pytest.mark.parametrize("name", sorted(_TEMPLATES))
    def test_the_title_is_positioned_and_the_profile_usable(self, name):
        profile = _profile(name)
        assert profile.title.positioned
        assert profile.usable
        assert profile.subtitle_font


class TestFurniture:
    """Furniture is what repeats. Cloning one slide's decoration wholesale
    swept up its content with it."""

    def test_a_layout_source_clones_nothing(self):
        """A slide built from the layout inherits the layout's decoration and
        the master's. Cloning them too would draw the logo twice."""
        assert _profile("attendo").furniture == []

    def test_a_slide_source_keeps_the_repeating_graphics(self):
        """Synsam's chart slides carry a rule under the title on every one of
        them — and a "5+6+7" label and an "n=1549 / 282 ..." line that are that
        slide's data, both short enough to have passed for a footer."""
        assert len(_profile("synsam").furniture) == 1

    def test_last_years_chart_does_not_travel(self):
        """The agent deck's own chart is a picture in the SAME box on all 20
        slides, so repetition alone would clone it onto every new slide. What
        survives is the backdrop and the accent bar beside the title."""
        profile = _profile("agent_deck")
        assert len(profile.furniture) == 2


class TestTheColoursComeOffTheSlide:
    """A template whose design lives on its slides does not state its brand in
    its theme. `attendo_agent_deck.pptx` renders cream and teal on every slide
    while its theme is untouched Office: white, black, and six colours nobody
    chose."""

    def test_the_ground_and_accent_are_read_from_the_shapes(self):
        profile = _profile("agent_deck")
        assert profile.background == "F7F3EC"
        assert profile.accent == "13615E"

    def test_a_rule_under_the_title_counts_as_the_accent(self):
        """Synsam draws no backdrop — its one repeating graphic is the orange
        rule under the title, and that is the colour its charts are in."""
        assert _profile("synsam").accent == "FF5000"

    def test_a_layout_template_leaves_them_to_the_theme(self):
        """There the theme IS the brand, and template_check already reads it."""
        profile = _profile("attendo")
        assert profile.background == ""
        assert profile.accent == ""


# ---------------------------------------------------------------------------
# Choosing the layout — the policy, with no file in sight
# ---------------------------------------------------------------------------
#
# The numbers below are measured from the three customer templates on staging.
# Kept as a pure function because the fault it fixes is a JUDGEMENT, not a
# reading: the reading was always right about Arla, and what it concluded from
# two slides was not.

from reportbuilder.render.template_check import LayoutCandidate  # noqa: E402
from reportbuilder.render.template_profile import choose_layout  # noqa: E402


def _cand(index, name, pct, score=10):
    return LayoutCandidate(index=index, name=name, score=score, has_title=True,
                           content_count=1, has_picture=False, content_area_pct=pct)


class TestChoosingTheLayout:
    def test_a_deck_says_where_its_design_lives(self):
        """Attendo: 42 of 56 slides on one layout. Usage IS the answer here,
        even against a candidate with a roomier content box."""
        cands = [_cand(3, "1 layout area", 45.0), _cand(9, "Big Picture", 70.0)]
        idx, take_geometry = choose_layout(cands, {"1 layout area": 42}, slide_count=56)
        assert idx == 3
        assert take_geometry is True

    def test_two_sample_slides_do_not_decide_anything(self):
        """Arla: 69 layouts, 27 candidates, and TWO slides. One of them landed
        on a sub-brand layout, which is how every rendered deck came out in Arla
        Protein branding with a black band."""
        cands = [_cand(36, "Sub Brand Protein 1", 22.2),
                 _cand(17, "Normal Text Diagram", 22.2),
                 _cand(60, "Cover_no subtitle", 1.9)]
        idx, _ = choose_layout(cands, {"Sub Brand Protein 1": 1}, slide_count=2)
        assert idx != 36, "one demo slide must not outvote 27 candidates"

    def test_a_column_is_not_a_chart_area(self):
        """Arla again: its best content box is 22% of the slide, because every
        Normal layout is two-column. The layout is still worth having — the
        band, the logo, the title style — but its box is not where a chart goes.
        """
        cands = [_cand(17, "Normal Text Diagram", 22.2)]
        idx, take_geometry = choose_layout(cands, {}, slide_count=2)
        assert idx == 17, "still used, for its ground and its title"
        assert take_geometry is False, "but we place the chart ourselves"

    def test_a_real_content_area_is_used(self):
        """Prima Pet 54.7%, Suomalainen Työ 61.9% — both are genuinely the
        slide's content area, and both were drawn to leave room for a footer."""
        for pct in (54.7, 61.9):
            idx, take_geometry = choose_layout([_cand(7, "Otsikko ja sisältö", pct)],
                                               {}, slide_count=3)
            assert (idx, take_geometry) == (7, True)

    def test_nothing_to_choose_from(self):
        assert choose_layout([], {}, slide_count=10) == (None, False)

    def test_a_deck_built_on_a_blank_layout_is_hand_drawn(self):
        """Synsam: 98 of 147 slides on "Tom", which is not a candidate at all.
        That is the signal the design was drawn by hand — falling back to the
        roomiest candidate would build it on a layout it never uses and lose the
        design entirely."""
        cands = [_cand(3, "Innehåll", 55.0)]
        assert choose_layout(cands, {"Tom": 98, "Innehåll": 2}, slide_count=147) == (None, False)
