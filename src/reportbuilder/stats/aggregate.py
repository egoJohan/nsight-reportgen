from __future__ import annotations
import atexit
import threading

import duckdb
import pandas as pd

# One connection per thread, kept for the life of it. duckdb.connect() costs
# ~15ms, which was being paid once per chart; a connection is not safe to share
# across threads, and a render is one thread.
_local = threading.local()

# Every connection handed out, with the thread it belongs to, so they can be
# closed before the interpreter finalizes. `threading.local()` cannot enumerate
# its own values, and a connection still open at finalization ABORTS the
# process — its C++ destructor calls back into the Python C-API
# (`PyEval_RestoreThread`) from a thread that is already exiting, and
# `pthread_exit`'s forced unwind cannot cross that frame, so std::terminate
# aborts. Invisible in a server that never exits; fatal for anything batch
# shaped. (tests/test_duckdb_exit.py)
#
# Held STRONGLY, so no connection is ever destroyed on its own dying thread —
# a weak reference let exactly that happen at shutdown. But a strong hold must
# be let go: it used to keep the connection of every thread that had ENDED, and
# with it a whole DuckDB database, worker threads and memory. Request threads
# come and go, so the server grew until the kernel killed it (staging,
# 2026-09-29, 7.4 GB). Each new connection therefore first closes those of
# finished threads, here, on a live one.
# (tests/suite/unit/stats/test_duckdb_connection_release.py)
_open: list[tuple[threading.Thread, object]] = []
_open_lock = threading.Lock()


def _connection():
    con = getattr(_local, "con", None)
    if con is None:
        # One thread: a chart's aggregate is a few thousand rows on one request
        # thread, and DuckDB's default pool (a worker per core) only multiplied
        # the threads and memory each live connection holds.
        con = _local.con = duckdb.connect(config={"threads": 1})
        with _open_lock:
            finished = [c for t, c in _open if not t.is_alive()]
            _open[:] = [(t, c) for t, c in _open if t.is_alive()]
            _open.append((threading.current_thread(), con))
        for old in finished:
            _close(old)
    return con


def open_connection_count() -> int:
    """Connections held now — live threads', plus finished ones' not yet
    closed. Bounded by the threads alive at the last connection opened."""
    with _open_lock:
        return len(_open)


def _close(con) -> None:
    try:
        con.close()
    except Exception:  # noqa: BLE001 — a connection that will not close
        pass           # must not abort the exit this exists to protect


@atexit.register
def _close_connections() -> None:
    """Close every connection handed out, before the interpreter finalizes."""
    with _open_lock:
        cons = [c for _t, c in _open]
        _open[:] = []
    for con in cons:
        _close(con)

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
        scan = data[[value_var]].copy()
        scan["__seg__"] = list(seg_series)
        seg_col: str | None = "__seg__"
    else:
        seg_col = classifying_var
        # Only the columns the SQL below names. Registering the whole frame made
        # duckdb walk every column of it to build the scan — on a survey with 690
        # variables that was ~900 column reads to count ONE, and the single
        # biggest cost in computing a chart.
        cols = [value_var] + ([seg_col] if seg_col and seg_col != value_var else [])
        scan = data[cols]
    con = _connection()
    con.register("d", scan)
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
    con.unregister("d")
    return counts
