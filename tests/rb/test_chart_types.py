"""Tests for Chart Type IDs and native/image capability table (REQ-C-13)."""

import pytest
from reportbuilder.model.chart_types import ChartType, Capability, CAPABILITIES, supports


class TestChartTypeEnum:
    """Test ChartType enum members and count."""

    def test_exactly_11_chart_types(self):
        """Verify exactly 11 ChartType members exist."""
        chart_types = list(ChartType)
        assert len(chart_types) == 11
        assert set(chart_types) == {
            ChartType.LINE,
            ChartType.PIE,
            ChartType.VERTICAL_BAR,
            ChartType.STACKED_VERTICAL_BAR,
            ChartType.HORIZONTAL_BAR,
            ChartType.STACKED_HORIZONTAL_BAR,
            ChartType.RADAR,
            ChartType.DOUGHNUT,
            ChartType.SCATTER,
            ChartType.FUNNEL,
            ChartType.COMBO,
        }


class TestCapability:
    """Test Capability frozen dataclass."""

    def test_capability_creation(self):
        """Verify Capability can be created with native, native_kind, image."""
        cap = Capability(native=True, native_kind="own", image=True)
        assert cap.native is True
        assert cap.native_kind == "own"
        assert cap.image is True

    def test_capability_frozen(self):
        """Verify Capability is frozen (immutable)."""
        cap = Capability(native=True, native_kind="own", image=True)
        with pytest.raises(AttributeError):
            cap.native = False


class TestCapabilitiesTable:
    """Test the CAPABILITIES dictionary."""

    def test_all_11_types_in_capabilities(self):
        """Verify CAPABILITIES has entries for all 11 ChartType members."""
        assert len(CAPABILITIES) == 11
        for chart_type in ChartType:
            assert chart_type in CAPABILITIES
            assert isinstance(CAPABILITIES[chart_type], Capability)

    def test_all_11_types_support_image(self):
        """Verify all 11 chart types support image rendering."""
        for chart_type in ChartType:
            cap = CAPABILITIES[chart_type]
            assert cap.image is True, f"{chart_type} must support image"

    def test_nine_own_native_types(self):
        """Verify exactly 9 types have native='own' native_kind."""
        own_types = {
            ChartType.LINE,
            ChartType.PIE,
            ChartType.VERTICAL_BAR,
            ChartType.STACKED_VERTICAL_BAR,
            ChartType.HORIZONTAL_BAR,
            ChartType.STACKED_HORIZONTAL_BAR,
            ChartType.RADAR,
            ChartType.DOUGHNUT,
            ChartType.SCATTER,
        }

        actual_own = {
            ct for ct in ChartType
            if CAPABILITIES[ct].native and CAPABILITIES[ct].native_kind == "own"
        }
        assert actual_own == own_types

    def test_funnel_native_stacked_bar_approx(self):
        """Verify FUNNEL has native=True and native_kind='stacked_bar_approx'."""
        cap = CAPABILITIES[ChartType.FUNNEL]
        assert cap.native is True
        assert cap.native_kind == "stacked_bar_approx"
        assert cap.image is True

    def test_combo_native_excluded(self):
        """Verify COMBO has native=False and native_kind='none'."""
        cap = CAPABILITIES[ChartType.COMBO]
        assert cap.native is False
        assert cap.native_kind == "none"
        assert cap.image is True


class TestSupportsFunction:
    """Test the supports(chart_type, mode) function."""

    def test_supports_image_all_11(self):
        """Verify supports(t, 'image') returns True for all 11 types."""
        for chart_type in ChartType:
            assert supports(chart_type, "image") is True

    def test_supports_native_nine_own(self):
        """Verify supports(t, 'native') returns True for the 9 'own' types."""
        own_types = {
            ChartType.LINE,
            ChartType.PIE,
            ChartType.VERTICAL_BAR,
            ChartType.STACKED_VERTICAL_BAR,
            ChartType.HORIZONTAL_BAR,
            ChartType.STACKED_HORIZONTAL_BAR,
            ChartType.RADAR,
            ChartType.DOUGHNUT,
            ChartType.SCATTER,
        }
        for chart_type in own_types:
            assert supports(chart_type, "native") is True

    def test_supports_native_funnel_true(self):
        """Verify supports(FUNNEL, 'native') returns True."""
        assert supports(ChartType.FUNNEL, "native") is True

    def test_supports_native_combo_false(self):
        """Verify supports(COMBO, 'native') returns False."""
        assert supports(ChartType.COMBO, "native") is False

    def test_supports_invalid_mode_raises_valueerror(self):
        """Verify supports(t, 'bogus') raises ValueError."""
        with pytest.raises(ValueError, match="unknown mode"):
            supports(ChartType.LINE, "bogus")
