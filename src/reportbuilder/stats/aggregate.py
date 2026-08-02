from __future__ import annotations
import duckdb
import pandas as pd

def aggregate_counts(data: pd.DataFrame, value_var: str,
                     classifying_var: str | None = None,
                     *, seg_series=None, seg_masks=None,
                     ) -> dict[tuple[float | None, str], int]:
    """Raw (unweighted, unrounded) cell counts keyed by (value_code, segment_label).
    segment_label is "Total" when there is no classifier; with one, both per-segment
    counts AND a "Total" aggregate are returned. NaN (Sysmis) rows are excluded.

    When `seg_series` is given it IS the segmentation (its string values are the
    segment keys, e.g. cross-tab combos); its keys are used as-is (no numeric cast).
    When `seg_masks` is given it IS the segmentation — one boolean mask per segment,
    which may OVERLAP, so counts are taken per mask rather than by a single GROUP BY
    (a respondent in two segments counts once in each). "Total" counts the union,
    matching base_rules.segment_bases. (spec 2026-08-02 §2.3)

    This is the seam datahive's D1 primitive later replaces (same core signature)."""
    if seg_masks is not None:
        counts: dict[tuple[float | None, str], int] = {}
        v = pd.to_numeric(data[value_var], errors="coerce")
        answered = v.notna()
        any_seg = pd.Series(False, index=data.index)
        for m in seg_masks.values():
            any_seg = any_seg | m
        for key, mask in list(seg_masks.items()) + [("Total", any_seg)]:
            sub = v[answered & mask]
            for code, cnt in sub.value_counts().items():
                counts[(float(code), str(key))] = int(cnt)
        return counts
    if seg_series is not None:
        data = data.assign(__seg__=list(seg_series))
        seg_col: str | None = "__seg__"
    else:
        seg_col = classifying_var
    con = duckdb.connect()
    con.register("d", data)
    counts: dict[tuple[float | None, str], int] = {}

    # The Total column sits on the SAME population as the per-segment bases (see
    # base_rules.segment_bases): a respondent the classifier does not cover belongs
    # to no segment and must not inflate the Total, or the Total column's
    # percentages exceed 100%. Without a classifier, every row counts.
    # (spec 2026-08-02 §0)
    where = f'"{value_var}" IS NOT NULL'
    if seg_col is not None:
        where += f' AND "{seg_col}" IS NOT NULL'
    total = con.execute(
        f'SELECT "{value_var}" AS v, COUNT(*) AS n FROM d WHERE {where} GROUP BY v'
    ).fetchall()
    for v, n in total:
        counts[(float(v), "Total")] = int(n)

    if seg_col is not None:
        rows = con.execute(
            f'SELECT "{value_var}" AS v, "{seg_col}" AS s, COUNT(*) AS n '
            f'FROM d WHERE "{value_var}" IS NOT NULL AND "{seg_col}" IS NOT NULL '
            f'GROUP BY v, s'
        ).fetchall()
        for v, s, n in rows:
            if seg_series is not None:
                seg_label = str(s)  # already a string combo key
            else:
                seg_label = str(int(s)) if float(s).is_integer() else str(s)
            counts[(float(v), seg_label)] = int(n)
    con.close()
    return counts
