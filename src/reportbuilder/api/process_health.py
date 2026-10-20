"""What this process holds, and a warning when it holds too much.

Staging's backend was killed for memory on 2026-09-29 and nobody knew for three
weeks: Docker restarted it, /readyz said ok, and the only trace was a line in
the VM's kernel log. Two leaks lay behind it — a DuckDB connection kept for
every request thread that had ever run (stats/aggregate.py), and LibreOffice's
helpers never reaped because the server was PID 1 — and the first shows
plainly in the numbers here. (`zombies` counts this process's own unreaped
children; with `init: true` orphaned helpers are reaped by the container's init
and no longer land here at all.)

Read from /proc and the cgroup: Linux, which is where this is deployed.
(tests/suite/integration/api/test_process_health.py)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

from reportbuilder.stats import aggregate

log = logging.getLogger(__name__)

_STARTED = time.monotonic()

#: The default warning threshold. The backend levels at about 1 GB under a
#: heavy preview load; the container's ceiling on staging is 5 GB.
DEFAULT_WARN_RSS_MB = 3072


def _status_kb(field: str) -> int:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith(field + ":"):
                return int(line.split()[1])
    return 0


def _zombie_children() -> int:
    """Children of this process that have exited and not been waited for."""
    me = str(os.getpid())
    n = 0
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as f:
                stat = f.read()
        except OSError:
            continue
        # The command name is parenthesised and may hold spaces; the fields
        # after it are fixed: state, then ppid.
        fields = stat[stat.rindex(")") + 2:].split()
        if fields[0] == "Z" and fields[1] == me:
            n += 1
    return n


def _memory_limit_mb() -> int | None:
    """The container's memory ceiling, or None when there is none."""
    try:
        with open("/sys/fs/cgroup/memory.max") as f:
            raw = f.read().strip()
    except OSError:
        return None
    return None if raw == "max" else int(raw) // (1024 * 1024)


def snapshot() -> dict:
    return {
        "rss_mb": _status_kb("VmRSS") // 1024,
        "peak_rss_mb": _status_kb("VmHWM") // 1024,
        "threads": _status_kb("Threads"),
        "duckdb_connections": aggregate.open_connection_count(),
        "zombies": _zombie_children(),
        "memory_limit_mb": _memory_limit_mb(),
        "uptime_seconds": int(time.monotonic() - _STARTED),
    }


def check(warn_rss_mb: int = DEFAULT_WARN_RSS_MB) -> dict:
    """Take a snapshot; log a warning when memory is past *warn_rss_mb*."""
    snap = snapshot()
    if snap["rss_mb"] > warn_rss_mb:
        log.warning(
            "backend memory high: rss=%s MB (warn at %s, limit %s) threads=%s "
            "duckdb_connections=%s zombies=%s",
            snap["rss_mb"], warn_rss_mb, snap["memory_limit_mb"] or "none",
            snap["threads"], snap["duckdb_connections"], snap["zombies"])
    return snap


def _env_number(name: str, default: float) -> float:
    """A typo in the environment must not stop the app or its shutdown: the
    default, and a warning saying which variable was ignored."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("%s=%r is not a number; using %s", name, raw, default)
        return default


async def watch() -> None:
    """Check every NSIGHT_PROCESS_WATCH_SECONDS (default 60; 0 turns it off),
    warning past NSIGHT_RSS_WARN_MB. Runs for the life of the app."""
    interval = _env_number("NSIGHT_PROCESS_WATCH_SECONDS", 60.0)
    if interval <= 0:
        return
    warn = int(_env_number("NSIGHT_RSS_WARN_MB", DEFAULT_WARN_RSS_MB))
    while True:
        await asyncio.sleep(interval)
        try:
            # Off the event loop: it walks /proc.
            await asyncio.to_thread(check, warn)
        except Exception:  # noqa: BLE001 — a watch must never take the app down
            log.debug("process check failed", exc_info=True)
