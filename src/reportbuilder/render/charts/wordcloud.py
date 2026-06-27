"""Word cloud plugin — free-text frequency cloud.

Not offered through generic suitability (returns None) and never auto-suggested:
the questions route wires word clouds explicitly for open-ended text questions
(and excludes them everywhere else). Image-only; native OOXML has no word-cloud
form, so it reuses the unsupported-native raiser."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import note_field
from reportbuilder.render.image.wordcloud import build_image_wordcloud
from reportbuilder.render.native.combo import build_combo_native


def suitability(question, series) -> float | None:
    """Always None — word cloud is wired explicitly for text questions, not via
    generic suitability (keeps it out of compatible types for normal questions)."""
    return None


register(ChartPlugin(
    id="wordcloud",
    label="Word Cloud",
    image_build=build_image_wordcloud,
    native_build=build_combo_native,  # no native word-cloud form (unsupported raiser)
    suitability=suitability,
    suggest=None,
    config_schema=(note_field(
        "Word cloud — shows the most frequently mentioned answer words; "
        "larger words were mentioned more often."
    ),),
))
