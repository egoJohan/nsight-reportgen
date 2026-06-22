from __future__ import annotations
import duckdb
import pandas as pd

def aggregate_counts(data: pd.DataFrame, value_var: str,
                     classifying_var: str | None = None,
                     ) -> dict[tuple[float | None, str], int]:
    """Raw (unweighted, unrounded) cell counts keyed by (value_code, segment_label).
    segment_label is "Total" when classifying_var is None; with a classifier, both
    per-segment counts AND a "Total" aggregate are returned. NaN (Sysmis) rows are
    excluded. This is the seam datahive's D1 primitive later replaces (same signature)."""
    con = duckdb.connect()
    con.register("d", data)
    counts: dict[tuple[float | None, str], int] = {}

    total = con.execute(
        f'SELECT "{value_var}" AS v, COUNT(*) AS n '
        f'FROM d WHERE "{value_var}" IS NOT NULL GROUP BY v'
    ).fetchall()
    for v, n in total:
        counts[(float(v), "Total")] = int(n)

    if classifying_var is not None:
        rows = con.execute(
            f'SELECT "{value_var}" AS v, "{classifying_var}" AS s, COUNT(*) AS n '
            f'FROM d WHERE "{value_var}" IS NOT NULL AND "{classifying_var}" IS NOT NULL '
            f'GROUP BY v, s'
        ).fetchall()
        for v, s, n in rows:
            counts[(float(v), str(int(s)) if float(s).is_integer() else str(s))] = int(n)
    con.close()
    return counts
