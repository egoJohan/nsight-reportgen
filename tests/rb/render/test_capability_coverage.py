"""Coverage gate: NATIVE_BUILDERS and IMAGE_BUILDERS must mirror CAPABILITIES (REQ-C-13).

Four assertions lock the registries to the capability table so a silent gap
between a new ChartType and its builder registration cannot go undetected.
"""
from __future__ import annotations

import pytest

from reportbuilder.model.chart_types import CAPABILITIES, ChartType
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.render.native import NATIVE_BUILDERS, NativeUnsupportedError
from reportbuilder.render.native.combo import build_combo_native

_ALL_VALUES = {t.value for t in ChartType}


def test_native_registry_keys_match_all_eleven():
    """NATIVE_BUILDERS must have exactly one entry per ChartType value (all 11)."""
    assert set(NATIVE_BUILDERS.keys()) == _ALL_VALUES


def test_native_combo_raises_others_build():
    """combo entry raises NativeUnsupportedError; all other 10 are real (non-raiser) builders.

    Cross-checks intent against CAPABILITIES:
    - native=True types → real builder (not build_combo_native)
    - native=False types (combo) → the raiser
    """
    # combo must raise
    with pytest.raises(NativeUnsupportedError):
        NATIVE_BUILDERS["combo"](None)  # raises before touching ctx

    # every native-capable key must be callable and not the raiser
    raiser_values = {t.value for t in ChartType if not CAPABILITIES[t].native}
    other_keys = _ALL_VALUES - raiser_values
    for key in other_keys:
        fn = NATIVE_BUILDERS[key]
        assert callable(fn), f"NATIVE_BUILDERS[{key!r}] is not callable"
        assert fn is not build_combo_native, (
            f"NATIVE_BUILDERS[{key!r}] is build_combo_native but should be a real builder"
        )

    # cross-check against CAPABILITIES
    for t in ChartType:
        cap = CAPABILITIES[t]
        builder = NATIVE_BUILDERS[t.value]
        if cap.native:
            # native-capable types must map to a real builder
            assert builder is not build_combo_native, (
                f"CAPABILITIES says {t.value!r} is native-capable but "
                f"NATIVE_BUILDERS maps it to the combo raiser"
            )
        else:
            # native=False types must map to the raiser
            assert builder is build_combo_native, (
                f"CAPABILITIES says {t.value!r} is NOT native-capable but "
                f"NATIVE_BUILDERS[{t.value!r}] is not the NativeUnsupportedError raiser"
            )


def test_image_registry_is_all_eleven():
    """IMAGE_BUILDERS must have exactly one entry per ChartType value (all 11)."""
    assert set(IMAGE_BUILDERS.keys()) == _ALL_VALUES


def test_image_is_superset_of_native_capable():
    """Every native-capable ChartType must also have an IMAGE_BUILDERS entry (image ≥ native)."""
    native_capable_values = {t.value for t in ChartType if CAPABILITIES[t].native}
    image_keys = set(IMAGE_BUILDERS.keys())
    missing = native_capable_values - image_keys
    assert not missing, (
        f"These native-capable types are missing from IMAGE_BUILDERS: {missing}"
    )
