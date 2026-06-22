"""Per-requirement Claude-judge rubrics (design §12). One rubric per judged gate."""
from __future__ import annotations

RUBRICS: dict[str, str] = {
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
}

def rubric_for(requirement_id: str) -> str:
    return RUBRICS[requirement_id]
