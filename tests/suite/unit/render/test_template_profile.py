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
