"""Combo ("yhdistelmä") is not available in native mode (design §9a) — use image mode."""
from __future__ import annotations
from reportbuilder.render.base import RenderContext


def build_combo_native(ctx: RenderContext):
    from reportbuilder.render.native import NativeUnsupportedError
    raise NativeUnsupportedError(
        "combo charts are not supported in native render mode; use image mode for combo"
    )
