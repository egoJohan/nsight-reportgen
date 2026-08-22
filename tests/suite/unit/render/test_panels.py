"""The one rule for which classifier groups become pie panels.

Read by the feasibility check, the image renderers and the methodology
footer alike — see docs/superpowers/specs/2026-08-22-multi-pie-panels-design.md.
"""
from __future__ import annotations

from reportbuilder.render.panels import MAX_PANELS, panel_segments
from reportbuilder.stats.series import Cell, SeriesResult


def _series(segments, bases) -> SeriesResult:
    cats = ("A", "B")
    cells = {(c, s): Cell(pct=50.0, count=1.0, mean=None)
             for c in cats for s in segments}
    return SeriesResult(categories=cats, segments=tuple(segments), cells=cells,
                        base_n=dict(bases), statistic="pct")


def test_no_classifier_is_not_split():
    sel = panel_segments(_series(("Total",), {"Total": 100}))
    assert sel.labels == ("Total",)
    assert sel.split is False
    assert sel.thin == () and sel.capped == () and sel.degraded is False


def test_total_is_never_a_panel():
    sel = panel_segments(_series(
        ("Naiset", "Miehet", "Total"),
        {"Naiset": 60, "Miehet": 40, "Total": 100}))
    assert sel.labels == ("Naiset", "Miehet")
    assert sel.split is True


def test_thin_group_is_dropped_and_named():
    sel = panel_segments(_series(
        ("Naiset", "Miehet", "Muut", "Total"),
        {"Naiset": 60, "Miehet": 40, "Muut": 8, "Total": 108}))
    assert sel.labels == ("Naiset", "Miehet")
    assert sel.thin == ("Muut",)


def test_cap_keeps_the_three_largest_in_segment_order():
    sel = panel_segments(_series(
        ("18-29", "30-44", "45-59", "60+", "Total"),
        {"18-29": 50, "30-44": 90, "45-59": 70, "60+": 30, "Total": 240}))
    # Largest three are 30-44, 45-59, 18-29 — but they DISPLAY in data order.
    assert sel.labels == ("18-29", "30-44", "45-59")
    assert sel.capped == ("60+",)
    assert len(sel.labels) == MAX_PANELS


def test_cap_ties_break_on_segment_order():
    sel = panel_segments(_series(
        ("A", "B", "C", "D", "Total"),
        {"A": 50, "B": 50, "C": 50, "D": 50, "Total": 200}))
    assert sel.labels == ("A", "B", "C")
    assert sel.capped == ("D",)


def test_all_groups_thin_degrades_to_total_not_to_nothing():
    sel = panel_segments(_series(
        ("Naiset", "Miehet", "Total"),
        {"Naiset": 4, "Miehet": 6, "Total": 10}))
    assert sel.labels == ("Total",)
    assert sel.degraded is True
    assert sel.split is True
    assert sel.thin == ("Naiset", "Miehet")


def test_one_surviving_group_still_counts_as_split():
    sel = panel_segments(_series(
        ("Naiset", "Miehet", "Total"),
        {"Naiset": 60, "Miehet": 3, "Total": 63}))
    assert sel.labels == ("Naiset",)
    assert sel.split is True
    assert sel.thin == ("Miehet",)


def test_panels_imports_standalone():
    """`panels` must not depend on the image package: importing it first used to
    raise ImportError through image/__init__ -> pie -> panels. (2026-08-22)"""
    import subprocess, sys
    r = subprocess.run([sys.executable, "-c", "import reportbuilder.render.panels"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
