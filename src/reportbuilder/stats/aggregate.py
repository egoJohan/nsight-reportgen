from __future__ import annotations
import duckdb
import pandas as pd

def aggregate_counts(data: pd.DataFrame, value_var: str,
                     classifying_var: str | None = None,
                     *, seg_series=None,
                     ) -> dict[tuple[float | None, str], int]:
    """Raw (unweighted, unrounded) cell counts keyed by (value_code, segment_label).
    segment_label is "Total" when there is no classifier; with one, both per-segment
    counts AND a "Total" aggregate are returned. NaN (Sysmis) rows are excluded.

    When `seg_series` is given it IS the segmentation (its string values are the
    segment keys, e.g. cross-tab combos); its keys are used as-is (no numeric cast).
    This is the seam datahive's D1 primitive later replaces (same core signature)."""
    if seg_series is not None:
        data = data.assign(__seg__=list(seg_series))
        seg_col: str | None = "__seg__"
    else:
        seg_col = classifying_var
    con = duckdb.connect()
    con.register("d", data)
    counts: dict[tuple[float | None, str], int] = {}

    total = con.execute(
        f'SELECT "{value_var}" AS v, COUNT(*) AS n '
        f'FROM d WHERE "{value_var}" IS NOT NULL GROUP BY v'
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
