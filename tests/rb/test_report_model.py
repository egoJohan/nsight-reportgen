"""Tests for the Report Model — report definition types (design §8)."""

import dataclasses
import pytest

from reportbuilder.model.report import SortSpec, NumberFormat, ElementToggles, ChartSpec, Report


class TestSortSpec:
    """Test SortSpec frozen dataclass."""

    def test_sort_spec_defaults(self):
        """Verify SortSpec defaults: descending=True, topbox_codes=()."""
        spec = SortSpec(basis="pct")
        assert spec.basis == "pct"
        assert spec.descending is True
        assert spec.topbox_codes == ()

    def test_sort_spec_topbox_codes_settable(self):
        """Verify topbox_codes can be set."""
        spec = SortSpec(basis="topbox_sum", topbox_codes=(4.0, 5.0))
        assert spec.topbox_codes == (4.0, 5.0)

    def test_sort_spec_descending_settable(self):
        """Verify descending can be set."""
        spec = SortSpec(basis="pct", descending=False)
        assert spec.descending is False

    def test_sort_spec_frozen(self):
        """Verify SortSpec is frozen (immutable)."""
        spec = SortSpec(basis="pct")
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.basis = "count"


class TestNumberFormat:
    """Test NumberFormat frozen dataclass."""

    def test_number_format_defaults(self):
        """Verify NumberFormat defaults: pct_decimals=0, mean_decimals=1, count_round_up=False, show_pct_sign=True."""
        fmt = NumberFormat()
        assert fmt.pct_decimals == 0
        assert fmt.mean_decimals == 1
        assert fmt.count_round_up is False
        assert fmt.show_pct_sign is True

    def test_number_format_settable(self):
        """Verify NumberFormat fields can be set."""
        fmt = NumberFormat(pct_decimals=2, mean_decimals=2, count_round_up=True, show_pct_sign=False)
        assert fmt.pct_decimals == 2
        assert fmt.mean_decimals == 2
        assert fmt.count_round_up is True
        assert fmt.show_pct_sign is False

    def test_number_format_frozen(self):
        """Verify NumberFormat is frozen (immutable)."""
        fmt = NumberFormat()
        with pytest.raises(dataclasses.FrozenInstanceError):
            fmt.pct_decimals = 2


class TestElementToggles:
    """Test ElementToggles frozen dataclass."""

    def test_element_toggles_all_defaults_true(self):
        """Verify ElementToggles defaults: all True."""
        toggles = ElementToggles()
        assert toggles.title is True
        assert toggles.legend is True
        assert toggles.n is True
        assert toggles.axis_names is True
        assert toggles.filter_var is True
        assert toggles.data_labels is True

    def test_element_toggles_settable(self):
        """Verify ElementToggles fields can be set."""
        toggles = ElementToggles(
            title=False,
            legend=False,
            n=False,
            axis_names=False,
            filter_var=False,
            data_labels=False
        )
        assert toggles.title is False
        assert toggles.legend is False
        assert toggles.n is False
        assert toggles.axis_names is False
        assert toggles.filter_var is False
        assert toggles.data_labels is False

    def test_element_toggles_frozen(self):
        """Verify ElementToggles is frozen (immutable)."""
        toggles = ElementToggles()
        with pytest.raises(dataclasses.FrozenInstanceError):
            toggles.title = False


class TestChartSpec:
    """Test ChartSpec frozen dataclass."""

    def test_chart_spec_build_with_defaults(self):
        """Verify ChartSpec can be built with scatter_xy default None."""
        spec = ChartSpec(
            question_ref="Q1",
            chart_type="bar",
            statistic="pct",
            classifying_var=None,
            number_format=NumberFormat(),
            sort=SortSpec(basis="pct"),
            template_slot="A1",
            elements=ElementToggles()
        )
        assert spec.question_ref == "Q1"
        assert spec.chart_type == "bar"
        assert spec.statistic == "pct"
        assert spec.classifying_var is None
        assert spec.scatter_xy is None

    def test_chart_spec_scatter_xy_settable(self):
        """Verify scatter_xy can be set."""
        spec = ChartSpec(
            question_ref="Q1",
            chart_type="scatter",
            statistic="mean",
            classifying_var=None,
            number_format=NumberFormat(),
            sort=SortSpec(basis="pct"),
            template_slot="A1",
            elements=ElementToggles(),
            scatter_xy=("x_var", "y_var")
        )
        assert spec.scatter_xy == ("x_var", "y_var")

    def test_chart_spec_with_classifying_var(self):
        """Verify ChartSpec can have classifying_var."""
        spec = ChartSpec(
            question_ref="Q2",
            chart_type="bar",
            statistic="count",
            classifying_var="segment",
            number_format=NumberFormat(),
            sort=SortSpec(basis="count"),
            template_slot="B1",
            elements=ElementToggles()
        )
        assert spec.classifying_var == "segment"

    def test_chart_spec_frozen(self):
        """Verify ChartSpec is frozen (immutable)."""
        spec = ChartSpec(
            question_ref="Q1",
            chart_type="bar",
            statistic="pct",
            classifying_var=None,
            number_format=NumberFormat(),
            sort=SortSpec(basis="pct"),
            template_slot="A1",
            elements=ElementToggles()
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.question_ref = "Q2"


class TestReport:
    """Test Report frozen dataclass."""

    def test_report_holds_charts_and_render_mode(self):
        """Verify Report holds a tuple of ChartSpec and render_mode."""
        chart1 = ChartSpec(
            question_ref="Q1",
            chart_type="bar",
            statistic="pct",
            classifying_var=None,
            number_format=NumberFormat(),
            sort=SortSpec(basis="pct"),
            template_slot="A1",
            elements=ElementToggles()
        )
        chart2 = ChartSpec(
            question_ref="Q2",
            chart_type="pie",
            statistic="pct",
            classifying_var=None,
            number_format=NumberFormat(),
            sort=SortSpec(basis="data_order"),
            template_slot="A2",
            elements=ElementToggles()
        )
        report = Report(
            name="Survey Results",
            render_mode="native",
            template_ref="template_1",
            charts=(chart1, chart2)
        )
        assert report.name == "Survey Results"
        assert report.render_mode == "native"
        assert report.template_ref == "template_1"
        assert report.charts == (chart1, chart2)
        assert len(report.charts) == 2

    def test_report_render_mode_image(self):
        """Verify Report can have render_mode='image'."""
        report = Report(
            name="Report",
            render_mode="image",
            template_ref="template_1",
            charts=()
        )
        assert report.render_mode == "image"

    def test_report_empty_charts(self):
        """Verify Report can hold empty tuple of charts."""
        report = Report(
            name="Empty Report",
            render_mode="native",
            template_ref="template_1",
            charts=()
        )
        assert report.charts == ()

    def test_report_frozen(self):
        """Verify Report is frozen (immutable)."""
        report = Report(
            name="Report",
            render_mode="native",
            template_ref="template_1",
            charts=()
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.name = "Different"
