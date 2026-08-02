"""Corpus guard for the coded-string rule (spec 2026-08-02 §1.1).

Runs only when the local client materials are present (they are gitignored IPR),
so a checkout without them skips rather than fails.
"""
from __future__ import annotations

import pathlib

import pytest

from reportbuilder.ingest.sav_reader import _is_coded_string, _is_metadata, read_sav

_STORE = pathlib.Path("work/demo-store/materials")

# (material, variable, expected measurement) — the cases that pin the thresholds.
_CASES = [
    ("mat-erisan.sav", "var214", "categorical"),    # the target: 2 values, ratio 255
    ("mat-erisan.sav", "var43", "text"),            # 52 distinct, ratio 1.1
    ("mat-207.sav", "Elamantilanne_muu", "text"),   # 5 distinct, ratio 1.0
    ("mat-207.sav", "Rooli_muu", "text"),           # 12 distinct, ratio 1.7
    ("mat-207.sav", "Perustelu", "text"),           # 371 distinct
    ("mat-99.sav", "var129", "categorical"),        # Branch A/B/C
    ("mat-99.sav", "var18", "categorical"),         # URL_profiili segments
]


@pytest.mark.parametrize("material,var,expected", _CASES)
def test_corpus_measurement(material, var, expected):
    path = _STORE / material
    if not path.exists():
        pytest.skip(f"{material} not available locally")
    _df, model = read_sav(str(path))
    assert model.variables[var].measurement == expected


def test_no_substantive_open_end_is_treated_as_a_coded_string():
    """Across every local material, the only NON-paradata columns the coded-string
    rule claims are the known concept/segment columns.

    Scoped to what the rule can actually change — a STRING column with no value
    labels. Numeric label-less categoricals (the 0/1 segment flags such as
    `Suosittelijat`) were already categorical and are none of this rule's business.

    If this fails, a real open-end is being misclassified: retune the ratio rather
    than widening `allowed`."""
    if not _STORE.exists():
        pytest.skip("local materials not available")
    allowed = {"var214", "var129", "var18"}
    unexpected = []
    for path in sorted(_STORE.glob("*.sav")):
        df, model = read_sav(str(path))
        for name, v in model.variables.items():
            if v.value_labels or name not in df.columns:
                continue
            if df[name].dtype != object:          # numeric flag, not our rule
                continue
            if not _is_coded_string(df[name]):
                continue
            if _is_metadata(name, v.label or name):
                continue
            if name not in allowed:
                unexpected.append(f"{path.name}:{name} ({v.label})")
    assert not unexpected, f"unexpected coded strings: {unexpected}"
