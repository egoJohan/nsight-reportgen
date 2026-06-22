"""Tests for rendering contracts (base.py)."""
import pytest
from dataclasses import FrozenInstanceError
from reportbuilder.render.base import Slot, StyleSpec, RenderContext, ChartRenderer
from reportbuilder.testing.fixtures import known_series, one_chart_report


class TestSlot:
    """Test Slot is a frozen dataclass with 6 named fields."""

    def test_slot_is_frozen_dataclass(self):
        """Create a Slot and verify it's frozen."""
        slot = Slot(slide_index=0, left=10, top=20, width=100, height=200, name="slot1")
        assert slot.slide_index == 0
        assert slot.left == 10
        assert slot.top == 20
        assert slot.width == 100
        assert slot.height == 200
        assert slot.name == "slot1"

    def test_slot_mutation_raises_frozen_instance_error(self):
        """Mutation of a frozen Slot should raise FrozenInstanceError."""
        slot = Slot(slide_index=0, left=10, top=20, width=100, height=200, name="slot1")
        with pytest.raises(FrozenInstanceError):
            slot.left = 20


class TestStyleSpec:
    """Test StyleSpec font_for and color_for methods."""

    def test_font_for_returns_arial_10(self):
        """StyleSpec().font_for() should return ('Arial', 10) for any element_class."""
        style = StyleSpec()
        font_name, font_size = style.font_for("title")
        assert font_name == "Arial"
        assert font_size == 10

    def test_font_for_different_element_classes(self):
        """font_for() should return ('Arial', 10) for any element class."""
        style = StyleSpec()
        assert style.font_for("legend") == ("Arial", 10)
        assert style.font_for("axis") == ("Arial", 10)
        assert style.font_for("label") == ("Arial", 10)

    def test_color_for_returns_hex_string(self):
        """color_for() should return a 6-char hex string."""
        style = StyleSpec()
        color = style.color_for(0)
        assert isinstance(color, str)
        assert len(color) == 6
        # Verify it's valid hex
        int(color, 16)

    def test_color_for_palette_wraps(self):
        """color_for(8) should wrap around and equal color_for(0) (palette has 8 colors)."""
        style = StyleSpec()
        assert style.color_for(0) == style.color_for(8)
        assert style.color_for(1) == style.color_for(9)
        assert style.color_for(7) == style.color_for(15)

    def test_color_for_different_indices(self):
        """color_for() should return different colors for different indices within palette."""
        style = StyleSpec()
        color0 = style.color_for(0)
        color1 = style.color_for(1)
        color7 = style.color_for(7)
        assert color0 != color1
        assert color1 != color7
        assert color0 != color7


class TestRenderContext:
    """Test RenderContext construction and field assignment."""

    def test_render_context_construction(self):
        """RenderContext should be constructible with Slot, StyleSpec, ChartSpec, SeriesResult, NumberFormat."""
        # Setup
        slot = Slot(slide_index=0, left=10, top=20, width=100, height=200, name="slot1")
        style = StyleSpec()
        series = known_series()
        report = one_chart_report()
        chart_spec = report.charts[0]
        fmt = chart_spec.number_format

        # Construct RenderContext
        ctx = RenderContext(
            slide=None,  # Use None as placeholder
            slot=slot,
            style=style,
            spec=chart_spec,
            series=series,
            fmt=fmt,
        )

        # Verify all fields are stored correctly
        assert ctx.slide is None
        assert ctx.slot is slot
        assert ctx.style is style
        assert ctx.spec is chart_spec
        assert ctx.series is series
        assert ctx.fmt is fmt
