"""Base (denominator) rules — the correctness spine (R1).

Getting a base wrong makes every percentage wrong.  These three functions
define what counts as a valid response for each question kind.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Variable


def _valid_mask(data: pd.DataFrame, var: Variable,
                missing_override: set[float] | None = None) -> pd.Series:
    s = pd.to_numeric(data[var.name], errors="coerce")
    missing = var.missing_values if missing_override is None else missing_override
    return s.notna() & ~s.isin(missing)


def single_base(data: pd.DataFrame, var: Variable, segment_filter=None,
                missing_override: set[float] | None = None) -> int:
    """Valid responses excluding the variable's user-missing set and NaN (Sysmis). (REQ-C-16, MV-01/02)

    When `missing_override` is provided it replaces `var.missing_values` for the
    "is this code missing" test — keeping the base consistent with an
    effective "Not answered" set (e.g. ChartSpec.not_answered_codes).
    """
    mask = _valid_mask(data, var, missing_override)
    if segment_filter is not None:
        mask = mask & segment_filter
    return int(mask.sum())


def multi_base(data: pd.DataFrame, vars_: list[Variable]) -> int:
    """Respondents who answered the set = those with >=1 valid selection (value==1)
    across the group. NOT the count of selections. (REQ-M-03)"""
    answered = pd.Series(False, index=data.index)
    for v in vars_:
        s = pd.to_numeric(data[v.name], errors="coerce")
        answered = answered | (s.notna() & ~s.isin(v.missing_values) & (s == 1.0))
    return int(answered.sum())


def _classifier_keep(seg: pd.Series, classifier_var: Variable | None) -> set[float] | None:
    """The classifier codes to KEEP as segments. Excludes the classifier's declared
    missing values and — when it carries any value labels — any present code that has
    NO label (an undeclared "no answer" sentinel like 99). Returns None (keep every
    present code) when there's no classifier Variable to judge by."""
    if classifier_var is None:
        return None
    present = {float(c) for c in seg.dropna().unique()}
    missing = {float(m) for m in (classifier_var.missing_values or ())}
    labeled = {float(vl.value) for vl in classifier_var.value_labels}
    keep = (present & labeled) if labeled else present
    return keep - missing


def segment_bases(data: pd.DataFrame, var: Variable, classifying_var: str | None = None,
                  missing_override: set[float] | None = None,
                  *, seg_series: pd.Series | None = None,
                  classifier_var: Variable | None = None) -> dict[str, int]:
    """Per-segment base + a "Total", each excluding missing in the reported var and
    the classifier. (REQ-C-14)

    When `missing_override` is provided it replaces `var.missing_values` for the
    "is this code missing" test (eff-aware base for ChartSpec.not_answered_codes).

    When `seg_series` is given it IS the segmentation (its values are the segment
    keys, e.g. cross-tab combo strings) and is used as-is — no numeric coercion.

    When `classifier_var` (the classifying variable's Variable) is given, classifier
    codes that are its missing values — or that carry no value label when it has any —
    are dropped, so a bare unlabelled sentinel (e.g. 99) never appears as a group.
    """
    valid = _valid_mask(data, var, missing_override)
    if seg_series is not None:
        bases: dict[str, int] = {"Total": int((valid & seg_series.notna()).sum())}
        for key in seg_series.dropna().unique():
            bases[str(key)] = int((valid & (seg_series == key)).sum())
        return bases
    seg = pd.to_numeric(data[classifying_var], errors="coerce")
    keep = _classifier_keep(seg, classifier_var)
    seg_valid = seg.isin(keep) if keep is not None else seg.notna()
    bases = {"Total": int((valid & seg_valid).sum())}
    for code in sorted(seg.dropna().unique()):
        if keep is not None and float(code) not in keep:
            continue
        label = str(int(code)) if float(code).is_integer() else str(code)
        bases[label] = int((valid & (seg == code)).sum())
    return bases
