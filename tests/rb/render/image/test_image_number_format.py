"""Unit tests for auto_decimals, format_value, and NumberFormat.mode (REQ-N-01/02/03).

Verifies:
- auto_decimals chooses 0 decimals for large pct values (≥10), 1 for small/close
- auto_decimals returns 1 decimal for Likert-style means, 0 for wide integer-ish range
- auto_decimals always returns 0 for count
- format_value routes auto/manual mode correctly and appends ' %' for pct
- NumberFormat.mode defaults to 'auto' and round-trips through JSON serde
"""
from __future__ import annotations

import pytest

from reportbuilder.render.image._mpl import auto_decimals, format_value
from reportbuilder.model.report import NumberFormat


# ---------------------------------------------------------------------------
# auto_decimals — pct
# ---------------------------------------------------------------------------

class TestAutoDecimalsPct:
    """REQ-N-01: percentage decimal selection based on value range."""

    def test_pct_large_values_zero_decimals(self):
        """pct of [86, 75, 42] → 0 decimals (all ≥ 10). REQ-N-01."""
        assert auto_decimals([86.0, 75.0, 42.0], "pct") == 0

    def test_pct_all_large_with_fracs_still_zero(self):
        """pct of [10.3, 12.7] → 0 decimals (all ≥ 10, even with fractions). REQ-N-01."""
        assert auto_decimals([10.3, 12.7], "pct") == 0

    def test_pct_small_value_with_fraction_one_decimal(self):
        """pct of [8.5, 3.2] → 1 decimal (any value < 10 with non-trivial fraction). REQ-N-01."""
        assert auto_decimals([8.5, 3.2], "pct") == 1

    def test_pct_close_spread_one_decimal(self):
        """pct with adjacent spread < 1 → 1 decimal. REQ-N-01."""
        assert auto_decimals([9.8, 10.1], "pct") == 1

    def test_pct_negligible_fractions_zero_decimals(self):
        """pct of [86.0, 75.0] → 0 decimals (fracs negligible). REQ-N-01."""
        assert auto_decimals([86.0, 75.0], "pct") == 0

    def test_pct_empty_values(self):
        """Empty pct values → 0 decimals (no data). REQ-N-01."""
        assert auto_decimals([], "pct") == 0


# ---------------------------------------------------------------------------
# auto_decimals — mean
# ---------------------------------------------------------------------------

class TestAutoDecimalsMean:
    """REQ-N-02: mean decimal selection by spread/magnitude."""

    def test_mean_close_small_values_one_decimal(self):
        """mean of [3.7, 3.8] → 1 decimal (Likert-style). REQ-N-02."""
        assert auto_decimals([3.7, 3.8], "mean") == 1

    def test_mean_likert_scale_one_decimal(self):
        """mean of [3.0, 4.0, 5.0] → 1 decimal (Likert-style, max ≤ 10). REQ-N-02."""
        assert auto_decimals([3.0, 4.0, 5.0], "mean") == 1

    def test_mean_wide_integer_range_zero_decimals(self):
        """mean of [10, 30, 50, 70] → 0 decimals (wide, integer-ish). REQ-N-02."""
        assert auto_decimals([10.0, 30.0, 50.0, 70.0], "mean") == 0

    def test_mean_single_value(self):
        """mean of [3.7] → 1 decimal. REQ-N-02."""
        assert auto_decimals([3.7], "mean") == 1

    def test_mean_empty_values(self):
        """Empty mean values → 1 decimal (safe default). REQ-N-02."""
        assert auto_decimals([], "mean") == 1


# ---------------------------------------------------------------------------
# auto_decimals — count
# ---------------------------------------------------------------------------

class TestAutoDecimalsCount:
    """REQ-N-03: count always uses 0 decimals (whole numbers)."""

    def test_count_always_zero(self):
        """count → 0 decimals regardless of values. REQ-N-03."""
        assert auto_decimals([5.0, 10.0, 15.0], "count") == 0

    def test_count_single_value(self):
        """count with single value → 0 decimals. REQ-N-03."""
        assert auto_decimals([42.0], "count") == 0

    def test_count_empty(self):
        """count with empty values → 0 decimals. REQ-N-03."""
        assert auto_decimals([], "count") == 0


# ---------------------------------------------------------------------------
# format_value — auto mode
# ---------------------------------------------------------------------------

class TestFormatValueAuto:
    """format_value in auto mode selects decimals from all_values. REQ-N-01/02/03."""

    def test_pct_auto_large_values_no_decimal(self):
        """Auto pct [86,75,42] → '86 %' (0 decimals, with sign). REQ-N-01."""
        fmt = NumberFormat(mode="auto")
        result = format_value(86.0, "pct", fmt, [86.0, 75.0, 42.0])
        assert result == "86 %"

    def test_pct_auto_small_value_one_decimal(self):
        """Auto pct [8.5,3.2] → '8.5 %'. REQ-N-01."""
        fmt = NumberFormat(mode="auto")
        result = format_value(8.5, "pct", fmt, [8.5, 3.2])
        assert result == "8.5 %"

    def test_pct_auto_no_sign(self):
        """Auto pct with show_pct_sign=False → '86' (no %%). REQ-N-01."""
        fmt = NumberFormat(mode="auto", show_pct_sign=False)
        result = format_value(86.0, "pct", fmt, [86.0, 75.0])
        assert result == "86"

    def test_mean_auto_one_decimal(self):
        """Auto mean [3.7,3.8] → '3.7'. REQ-N-02."""
        fmt = NumberFormat(mode="auto")
        result = format_value(3.7, "mean", fmt, [3.7, 3.8])
        assert result == "3.7"

    def test_count_auto_integer(self):
        """Auto count → integer string. REQ-N-03."""
        fmt = NumberFormat(mode="auto")
        result = format_value(42.0, "count", fmt, [42.0, 10.0])
        assert result == "42"

    def test_no_fmt_defaults_to_auto(self):
        """format_value with fmt=None uses auto mode. REQ-N-01."""
        result = format_value(86.0, "pct", None, [86.0, 75.0])
        assert result == "86 %"


# ---------------------------------------------------------------------------
# format_value — manual mode
# ---------------------------------------------------------------------------

class TestFormatValueManual:
    """format_value in manual mode uses explicit NumberFormat decimals. REQ-N-01/02."""

    def test_pct_manual_zero_decimals(self):
        """Manual pct with pct_decimals=0 → '75 %'. REQ-N-01."""
        fmt = NumberFormat(mode="manual", pct_decimals=0)
        result = format_value(75.0, "pct", fmt, [75.0, 30.0])
        assert result == "75 %"

    def test_pct_manual_one_decimal(self):
        """Manual pct with pct_decimals=1 → '75.0 %'. REQ-N-01."""
        fmt = NumberFormat(mode="manual", pct_decimals=1)
        result = format_value(75.0, "pct", fmt, [75.0])
        assert result == "75.0 %"

    def test_mean_manual_two_decimals(self):
        """Manual mean with mean_decimals=2 → '3.70'. REQ-N-02."""
        fmt = NumberFormat(mode="manual", mean_decimals=2)
        result = format_value(3.7, "mean", fmt, [3.7, 3.8])
        assert result == "3.70"

    def test_count_manual_always_integer(self):
        """Manual count always 0 decimals. REQ-N-03."""
        fmt = NumberFormat(mode="manual")
        result = format_value(100.0, "count", fmt)
        assert result == "100"


# ---------------------------------------------------------------------------
# NumberFormat.mode defaults and round-trip
# ---------------------------------------------------------------------------

class TestNumberFormatMode:
    """NumberFormat.mode field and JSON round-trip. REQ-N-01/02/03."""

    def test_mode_defaults_to_auto(self):
        """NumberFormat() default mode is 'auto'. REQ-N-01."""
        fmt = NumberFormat()
        assert fmt.mode == "auto"

    def test_mode_manual_settable(self):
        """NumberFormat(mode='manual') stores 'manual'."""
        fmt = NumberFormat(mode="manual")
        assert fmt.mode == "manual"

    def test_mode_round_trips_json(self):
        """NumberFormat.mode survives report_to_json/report_from_json. REQ-N-01."""
        from reportbuilder.model.report import (
            ChartSpec, ElementToggles, Report, SortSpec,
            report_to_json, report_from_json,
        )
        chart = ChartSpec(
            question_ref="q1",
            chart_type="bar",
            statistic="pct",
            classifying_var=None,
            number_format=NumberFormat(mode="auto"),
            sort=SortSpec(basis="pct"),
            template_slot="slot1",
            elements=ElementToggles(),
        )
        report = Report(
            name="R", render_mode="native", template_ref="t", charts=(chart,)
        )
        restored = report_from_json(report_to_json(report))
        assert restored.charts[0].number_format.mode == "auto"

    def test_mode_manual_round_trips_json(self):
        """NumberFormat(mode='manual') round-trips through JSON. REQ-N-01."""
        from reportbuilder.model.report import (
            ChartSpec, ElementToggles, Report, SortSpec,
            report_to_json, report_from_json,
        )
        chart = ChartSpec(
            question_ref="q1",
            chart_type="bar",
            statistic="mean",
            classifying_var=None,
            number_format=NumberFormat(mode="manual", mean_decimals=2),
            sort=SortSpec(basis="mean"),
            template_slot="slot1",
            elements=ElementToggles(),
        )
        report = Report(
            name="R", render_mode="native", template_ref="t", charts=(chart,)
        )
        restored = report_from_json(report_to_json(report))
        assert restored.charts[0].number_format.mode == "manual"
        assert restored.charts[0].number_format.mean_decimals == 2

    def test_missing_mode_in_json_defaults_to_auto(self):
        """JSON without 'mode' field deserializes NumberFormat with mode='auto'. REQ-N-01."""
        import json
        from reportbuilder.model.report import report_from_json
        # Simulate legacy JSON without 'mode' field
        data = {
            "name": "R",
            "render_mode": "native",
            "template_ref": "t",
            "charts": [
                {
                    "question_ref": "q1",
                    "chart_type": "bar",
                    "statistic": "pct",
                    "classifying_var": None,
                    "number_format": {
                        "pct_decimals": 0,
                        "mean_decimals": 1,
                        "count_round_up": False,
                        "show_pct_sign": True,
                        # no 'mode' key — legacy JSON
                    },
                    "sort": {"basis": "pct", "topbox_codes": [], "descending": True},
                    "template_slot": "slot1",
                    "elements": {
                        "title": True, "legend": True, "n": True,
                        "axis_names": True, "filter_var": True, "data_labels": True,
                    },
                    "scatter_xy": None,
                }
            ],
        }
        report = report_from_json(data)
        assert report.charts[0].number_format.mode == "auto"
