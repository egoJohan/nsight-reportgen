"""TDD tests for combo chart exclusion from native mode (Task 5.10).

Combo ("yhdistelmä") is not supported in native mode (design §9a).
The registry must have a "combo" entry that raises a clear error.
REQ-C-13.
"""
from __future__ import annotations
import pytest
from reportbuilder.render.native import NATIVE_BUILDERS, NativeUnsupportedError
from reportbuilder.render.native.combo import build_combo_native


def test_combo_native_raises():
    """Calling build_combo_native() raises NativeUnsupportedError with helpful message."""
    with pytest.raises(NativeUnsupportedError) as exc:
        build_combo_native(None)

    msg = str(exc.value).lower()
    assert "combo" in msg
    assert "image mode" in msg


def test_combo_registered():
    """Combo is registered in NATIVE_BUILDERS and points to build_combo_native."""
    assert "combo" in NATIVE_BUILDERS
    assert NATIVE_BUILDERS["combo"] is build_combo_native
