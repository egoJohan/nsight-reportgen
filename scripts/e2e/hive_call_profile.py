"""How many hive round-trips each nSight endpoint costs.

The hive serves requests one at a time (a single uvicorn process: measured at
131% CPU with 8 cores available, and latency that scales linearly with
concurrency). So the only lever on the nSight side is making FEWER calls, and
the first thing to know is where they go.

Counting is done from the hive container's own request log rather than by
instrumenting nSight, so it sees every call the request really makes —
including the ones made by dependencies, which is exactly where they were
hiding: a GET of one report cost 80 hive requests, 56 of them sidecar reads for
OTHER reports.

    .venv/bin/python scripts/e2e/hive_call_profile.py --case case-x --material mat-x
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import urllib.error
import urllib.request

API = "http://localhost:8200"
# The container log carries postgres output as well as the API's. Only lines
# that are an HTTP request line are calls; counting everything inflated a report
# GET from 74 to whatever postgres happened to log alongside it.
REQ_RE = re.compile(r'"(GET|PUT|POST|DELETE|HEAD|PATCH) (/[^ "]*)')
# The container runs the entrance AND the hive behind it, and BOTH log the same
# logical call, so every count came out exactly doubled. The forwarded, internal
# hop reports a source port of 0; a call arriving from nSight has a real
# ephemeral port. Count only the latter, or every number here is 2x the truth.
SOURCE_RE = re.compile(r"([0-9.]+):([0-9]+) - \"")
PATH_RE = re.compile(r"path=([^\s\"&]+)")
ID_RE = re.compile(r"(usr|sess|rep|mat|cust|case)-[0-9a-f]+")


def _log_lines(container: str) -> list[bytes]:
    """The container log, both streams MERGED IN TIME ORDER.

    `capture_output=True` then `stdout + stderr` concatenates the two as
    separate blocks, so a tail slice lands entirely in one stream and misses
    the interleaved lines — which is why this counted zero API calls while the
    same thing done with `2>&1` in a shell counted 84.
    """
    out = subprocess.run(["docker", "logs", container],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return out.stdout.splitlines()


def log_len(container: str) -> int:
    return len(_log_lines(container))


def log_tail(container: str, n: int) -> list[str]:
    if n <= 0:
        return []
    return [l.decode("utf-8", "replace") for l in _log_lines(container)[-n:]]


def call(cookie: str, method: str, path: str, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Cookie": f"nsight_session={cookie}",
                 "Content-Type": "application/json"})
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
            return r.status, time.monotonic() - t
    except urllib.error.HTTPError as e:
        e.read()
        return e.code, time.monotonic() - t


def profile(container: str, cookie: str, label: str, method: str, path: str,
            body=None, settle: float = 1.0) -> dict:
    before = log_len(container)
    status, secs = call(cookie, method, path, body)
    time.sleep(settle)                       # let the hive flush its log
    after = log_len(container)
    lines = log_tail(container, after - before)
    paths: dict[str, int] = {}
    calls = 0
    for line in lines:
        req = REQ_RE.search(line)
        if not req:
            continue                      # postgres chatter, not an API call
        src = SOURCE_RE.search(line)
        if src and src.group(2) == "0":
            continue                      # the entrance's internal forward
        calls += 1
        m = PATH_RE.search(line)
        if m:
            key = ID_RE.sub(r"\1-X", m.group(1).replace("%2F", "/"))
        else:
            key = req.group(2).split("?")[0]
        paths[key] = paths.get(key, 0) + 1
    return {"label": label, "status": status, "secs": secs,
            "calls": calls, "paths": paths}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--material", required=True)
    ap.add_argument("--cookie", default="work/mu/johan.cookie")
    ap.add_argument("--container", default="egohive-nsight")
    ap.add_argument("--top", type=int, default=3)
    a = ap.parse_args()
    cookie = open(a.cookie).read().strip()

    st, _ = call(cookie, "GET", f"/cases/{a.case}/reports")
    rid = ""
    try:
        req = urllib.request.Request(
            f"{API}/cases/{a.case}/reports",
            headers={"Cookie": f"nsight_session={cookie}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            rid = (json.load(r)["reports"] or [{}])[0].get("report_id", "")
    except Exception as e:  # noqa: BLE001
        print(f"could not find a report: {e}")
        return 1

    doc = None
    try:
        req = urllib.request.Request(
            f"{API}/cases/{a.case}/reports/{rid}",
            headers={"Cookie": f"nsight_session={cookie}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            doc = json.load(r)
    except Exception:  # noqa: BLE001
        pass

    checks = [
        ("GET  /cases", "GET", "/cases", None),
        ("GET  /cases/{c}/materials", "GET", f"/cases/{a.case}/materials", None),
        ("GET  /cases/{c}/reports", "GET", f"/cases/{a.case}/reports", None),
        ("GET  report", "GET", f"/cases/{a.case}/reports/{rid}", None),
        ("POST report lock", "POST",
         f"/cases/{a.case}/reports/{rid}/lock?tab=profile", None),
        ("GET  material questions", "GET", f"/materials/{a.material}/questions", None),
        ("GET  sensitive-terms", "GET", f"/materials/{a.material}/sensitive-terms", None),
    ]
    if doc is not None:
        checks.append(("PUT  report (save)", "PUT",
                       f"/cases/{a.case}/reports/{rid}", doc))

    print(f"{'endpoint':<28} {'hive calls':>10} {'time':>8}   dominant paths")
    print("-" * 96)
    total = 0
    for label, method, path, body in checks:
        r = profile(a.container, cookie, label, method, path, body)
        total += r["calls"]
        top = sorted(r["paths"].items(), key=lambda kv: -kv[1])[:a.top]
        detail = "  ".join(f"{k}×{v}" for k, v in top) or "-"
        flag = "" if r["status"] < 400 else f"  [HTTP {r['status']}]"
        print(f"{label:<28} {r['calls']:>10} {r['secs']:>7.2f}s   {detail}{flag}")
    print("-" * 96)
    print(f"{'TOTAL':<28} {total:>10}")
    call(cookie, "DELETE", f"/cases/{a.case}/reports/{rid}/lock?tab=profile")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
