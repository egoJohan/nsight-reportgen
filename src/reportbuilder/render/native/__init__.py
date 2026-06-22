"""Native chart builders registry (design §9a). Keys are canonical chart_type ids."""
from __future__ import annotations
from reportbuilder.render.native.column import build_column_chart, build_vertical_bar  # noqa: F401

# Canonical key per plan §C1 (vertical_bar = COLUMN). Task 5.4 converges to
# the RenderContext (ctx) signature; build_column_chart remains importable for
# low-level / spike usage.
NATIVE_BUILDERS: dict[str, object] = {
    "vertical_bar": build_vertical_bar,
}
