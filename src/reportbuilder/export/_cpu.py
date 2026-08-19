"""How many cores this process may actually use.

`os.cpu_count()` reports the machine's cores, not the ones we are allowed on. A
render pinned with `taskset` — or a container given one core — would still slice
its deck six ways and start six LibreOffice processes on a single CPU, paying
six startups for parallelism that cannot happen. Affinity is what to ask.

(A cgroup CPU *quota* is invisible to both; there is no stdlib call for it, and
a host that limits that way will simply see the parallel paths behave as if it
had more cores.)
"""
from __future__ import annotations

import os


def usable_cores() -> int:
    """Cores this process is scheduled on; at least 1."""
    count = getattr(os, "process_cpu_count", None)
    if count is not None:                       # Python 3.13+: affinity-aware
        return max(1, count() or 1)
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):           # not Linux
        return max(1, os.cpu_count() or 1)


def workers_for(cap: int) -> int:
    """Parallel workers to run: one per usable core less one for the server,
    never more than *cap* and never fewer than 1."""
    return max(1, min(cap, usable_cores() - 1))
