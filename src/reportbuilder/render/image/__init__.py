"""Image-mode chart builders registry (Task 5.11).

IMAGE_BUILDERS maps canonical chart_type ids to callables (ctx -> None).
Builders self-register by importing this dict and assigning their key.
"""
from __future__ import annotations

IMAGE_BUILDERS: dict[str, object] = {}

# Trigger self-registration of bar/column builders
from reportbuilder.render.image import bars  # noqa: F401, E402
# Trigger self-registration of line builder
from reportbuilder.render.image import line  # noqa: F401, E402
