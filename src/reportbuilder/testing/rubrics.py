"""Per-requirement Claude-judge rubrics (design §12). One rubric per judged gate."""
from __future__ import annotations

RUBRICS: dict[str, str] = {
    "REQ-C-05": (
        "You are judging a screenshot of a survey question browser panel "
        "(REQ-C-05).\n"
        "PASS only if ALL of the following hold:\n"
        "1. Questions are displayed in a clear list — one row per question.\n"
        "2. Each row shows readable question text (not placeholder boxes, "
        "even if using a fallback font).\n"
        "3. Each row has an obvious single/multi control (e.g. a segmented "
        "button or toggle labelled 'single' / 'multi') so a survey analyst "
        "can classify each question.\n"
        "4. A sort control is visible somewhere in the panel (e.g. a "
        "dropdown labelled 'Sort by:').\n"
        "5. A survey analyst could scan and understand the question list "
        "at a glance.\n"
        "FAIL if the question list is absent, unreadable, or lacks the "
        "single/multi control or sort control."
    ),
    "REQ-U-11": (
        "You are judging a screenshot of a report builder screen "
        "(REQ-U-11).\n"
        "PASS only if ALL of the following hold:\n"
        "1. A question list is visible (on the left or in a panel) so the "
        "user can choose which questions to chart.\n"
        "2. At least one chart card (or the equivalent configuration area) "
        "is visible with a chart-type control (e.g. a dropdown labelled "
        "'Chart type').\n"
        "3. A statistic control (e.g. 'Statistic' dropdown) is present per "
        "chart card.\n"
        "4. The layout makes it clear — even to a non-technical user — how "
        "to pick a question and configure the resulting chart.\n"
        "FAIL if the question list is missing, if no chart configuration "
        "controls are visible, or if the layout is confusing."
    ),
    "R3-LAYOUT": (
        "You are judging a single rendered survey chart for layout cleanliness.\n"
        "PASS only if ALL hold:\n"
        "1. No text labels overlap each other or overlap the plotted bars/lines.\n"
        "2. No category, axis, legend, or data label is truncated or clipped at an edge.\n"
        "3. Every data label is fully legible (not overlapping its bar, not cut off).\n"
        "4. The chart reads as clean and presentation-quality.\n"
        "FAIL if any label is overlapping, truncated, clipped, or illegible."
    ),
    "REQ-C-24": (
        "You are judging a rendered survey chart exported to PNG for chart cleanliness "
        "(REQ-C-24).\n"
        "PASS only if ALL of the following hold:\n"
        "1. The chart renders the correct requested chart type (e.g. bar, horizontal bar, "
        "radar, funnel, or combo as specified in extra_context).\n"
        "2. All data labels are fully legible and non-overlapping — no label overlaps "
        "another label, a bar segment, a line, or the chart boundary.\n"
        "3. No category label, axis label, or legend label is truncated or clipped at any "
        "edge of the chart or slide.\n"
        "4. A legend is present and legible when the chart has 2 or more data series.\n"
        "5. An N= annotation (sample size) is visible somewhere on the slide.\n"
        "6. The chart reads as clean and presentation-quality — no overlapping elements, "
        "no garbled text, no obvious rendering artefacts.\n"
        "FAIL if any single criterion above is violated."
    ),
    "REQ-C-28b": (
        "You are judging a multi-page rendered survey report PDF for presentation quality "
        "(REQ-C-28b).\n"
        "PASS only if ALL of the following hold on every page:\n"
        "1. No text labels overlap each other or overlap the plotted bars/lines/segments.\n"
        "2. No category label, axis label, legend label, or data label is truncated or "
        "clipped at any edge of the chart or slide.\n"
        "3. Every data label is fully legible (no overlap with its bar, no cut-off at "
        "the slide boundary).\n"
        "4. The overall slide layout looks clean and presentation-quality — appropriate "
        "whitespace, no garbled text, no visible rendering artefacts.\n"
        "FAIL if any single criterion above is violated on any page."
    ),
}

def rubric_for(requirement_id: str) -> str:
    return RUBRICS[requirement_id]
