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
}

def rubric_for(requirement_id: str) -> str:
    return RUBRICS[requirement_id]
