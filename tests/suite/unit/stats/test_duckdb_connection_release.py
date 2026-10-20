"""A DuckDB connection must not outlive the thread that opened it.

`stats/aggregate.py` keeps one connection per thread. To close them before the
interpreter finalizes (tests/test_duckdb_exit.py) every connection was also put
in a module list — a strong reference, so the connection of a thread that had
ENDED was never released. Request threads come and go (the server's thread
pool, the per-request executors in export/), and each one left behind a whole
DuckDB database: its worker threads and its memory.

On staging that grew the backend to 7.4 GB until the kernel killed it
(2026-09-29); three weeks after the restart it held 2.7 GB and 285 idle
threads, about ninety abandoned connections.
"""
from __future__ import annotations

import gc
import threading
import weakref

import pandas as pd

from reportbuilder.stats import aggregate as ag

_DATA = pd.DataFrame({"q": [1, 2, 3, 1, 2] * 200, "seg": [1, 2] * 500})


def _os_threads() -> int:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("Threads:"):
                return int(line.split()[1])
    raise AssertionError("no Threads: line in /proc/self/status")


def _on_a_thread_that_ends(fn) -> None:
    t = threading.Thread(target=fn)
    t.start()
    t.join()


def test_a_finished_threads_connection_is_released_by_the_next_one_opened():
    """Not when its thread ends: it is closed from a LIVE thread, because one
    destroyed on its own exiting thread at shutdown aborts the process."""
    refs = []
    _on_a_thread_that_ends(lambda: refs.append(weakref.ref(ag._connection())))
    _on_a_thread_that_ends(ag._connection)
    gc.collect()

    assert refs[0]() is None, (
        "the connection of a thread that has ended is still alive; every "
        "request thread leaks one DuckDB database")


def test_short_lived_threads_do_not_accumulate_os_threads():
    def work():
        ag.aggregate_counts(_DATA, "q", "seg")

    _on_a_thread_that_ends(work)  # imports and lazy setup, outside the count
    gc.collect()
    before = _os_threads()

    for _ in range(10):
        _on_a_thread_that_ends(work)
    gc.collect()

    assert _os_threads() - before <= 1, (
        f"{_os_threads() - before} threads left behind by 10 finished "
        f"requests; each abandoned connection keeps its DuckDB workers")


def test_a_connection_runs_its_query_on_the_calling_thread():
    """A chart's aggregate is a few thousand rows on one request thread;
    DuckDB's default pool (one worker per core) only multiplies the threads
    and memory each live connection holds."""
    threads = ag._connection().execute(
        "SELECT current_setting('threads')").fetchone()[0]

    assert threads == 1
