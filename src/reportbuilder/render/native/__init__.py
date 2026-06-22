"""Native chart builders registry (design §9a). Keys are canonical chart_type ids."""
from __future__ import annotations
from reportbuilder.render.native.column import build_column_chart

# Canonical key per plan §C1 (vertical_bar = COLUMN). Phase 5 Task 5.4 converges
# build_column_chart to the (ctx) signature; the spike uses the positional form.
NATIVE_BUILDERS: dict[str, object] = {
    "vertical_bar": build_column_chart,
}
