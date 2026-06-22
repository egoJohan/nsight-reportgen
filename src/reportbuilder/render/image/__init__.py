"""Image-mode chart builders registry (Task 5.11).

IMAGE_BUILDERS maps canonical chart_type ids to callables (ctx -> None).
Registration is explicit here, mirroring the native builders pattern.
"""
from __future__ import annotations

from reportbuilder.render.image.bars import (  # noqa: F401
    build_image_column,
    build_image_bar,
    build_image_column_stacked,
    build_image_bar_stacked,
)
from reportbuilder.render.image.line import build_image_line  # noqa: F401

IMAGE_BUILDERS: dict[str, object] = {
    "vertical_bar": build_image_column,
    "horizontal_bar": build_image_bar,
    "stacked_vertical_bar": build_image_column_stacked,
    "stacked_horizontal_bar": build_image_bar_stacked,
    "line": build_image_line,
}
