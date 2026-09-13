"""One case, one command.

The first thing built, before any matrix exists, because everything after it is
debugged through it: when a rule fails on case 4,812 of a 15-minute run, the
question is always "show me that one picture, now". A gate you cannot ask about
a single case is a gate nobody trusts.

It reads the same `*.jsonl` case records the generator will later produce, so
phase 4 adds lines rather than changing the interface. A record is:

    {"id": ..., "study": ..., "template": ..., "spec": {...}}

`study` and `template` are names resolved against a small registry — for now
the synthetic SAV and the house template, which need no corpus. (Johan, 2026-09-12)
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

_REPO = pathlib.Path(__file__).resolve().parents[2]
_RUN = _REPO / "acceptance" / "run"

_CASE = {
    "id": "synthetic-default-vbar",
    "study": "synthetic",
    "template": "default",
    "spec": {
        "chart_type": "vertical_bar",
        "statistic": "pct",
        "classifying_var": None,
        "number_format": {"mode": "auto"},
        "sort": {"basis": "data_order", "descending": True},
        "template_slot": "s1",
        "elements": {},
    },
}


def _index(tmp_path) -> pathlib.Path:
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(_CASE) + "\n", encoding="utf-8")
    return path


def test_it_renders_one_named_case_and_reports_the_path_that_drew_it(tmp_path):
    """The whole deliverable: name a case, get its picture and know how it was
    drawn — in seconds, with no matrix and no corpus."""
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, str(_RUN), _CASE["id"],
         "--index", str(_index(tmp_path)), "--out", str(out)],
        capture_output=True, text=True, timeout=300, cwd=str(_REPO),
    )

    assert proc.returncode == 0, (
        f"the runner did not exit cleanly\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    picture = out / f"{_CASE['id']}.png"
    assert picture.exists(), f"no picture written\n{proc.stdout[-2000:]}"
    assert picture.read_bytes()[:4] == b"\x89PNG"
    # Which rasteriser drew it is the first question of any investigation.
    assert "composited" in proc.stdout, proc.stdout[-2000:]


def test_it_judges_the_picture_it_renders(tmp_path):
    """A picture the runner cannot judge is just a picture.

    The whole point of the suite is the verdict, and the first duty is overlap:
    no text printed over any other. The oracle reads matplotlib artists, which
    exist only while the figure is being saved — the served PNG is far too late
    — so the harness has to judge at the `Figure.savefig` seam during the
    render, not afterwards.
    """
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, str(_RUN), _CASE["id"],
         "--index", str(_index(tmp_path)), "--out", str(out)],
        capture_output=True, text=True, timeout=300, cwd=str(_REPO),
    )

    assert proc.returncode == 0, f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
    # Anchored, for the same reason as the legibility check below: a substring
    # test can be satisfied by the tmp_path echoed in the `picture` line.
    reported = [line.strip() for line in proc.stdout.splitlines()]
    assert any(line.startswith("overlaps") for line in reported), (
        f"the runner rendered a picture but said nothing about whether any "
        f"text collides:\n{proc.stdout[-2000:]}")


def test_it_reports_legibility_as_well_as_overlap(tmp_path):
    """A rule that nothing calls is not a gate, it is a test fixture.

    The overlap oracle is wired in; the legibility one was not, so the runner
    rendered a picture and said nothing about whether any type had shrunk past
    its floor. Both floors are judged at the same `Figure.savefig` seam, from
    the same census, so there is no reason for one to be reported and the other
    to be invisible.
    """
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, str(_RUN), _CASE["id"],
         "--index", str(_index(tmp_path)), "--out", str(out)],
        capture_output=True, text=True, timeout=300, cwd=str(_REPO),
    )

    assert proc.returncode == 0, f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
    # Anchored to the start of a line, NOT `in stdout`: pytest names tmp_path
    # after the test function, so the runner's `picture` line echoes
    # "...test_it_reports_legibility_as_w0/out/..." and a substring check
    # passes on this test's own name. It did, before this was tightened.
    reported = [line.strip() for line in proc.stdout.splitlines()]
    assert any(line.startswith("legibility") for line in reported), (
        f"the runner judged overlap but never mentioned type size:\n"
        f"{proc.stdout[-2000:]}")


def test_it_works_as_the_bare_command_it_is_documented_as(tmp_path):
    """`acceptance/run <case-id>`, exactly as a person types it.

    The other tests hand the file to `sys.executable`, which bypasses the
    shebang — so they all passed while the documented command was broken:
    `#!/usr/bin/env python3` finds the SYSTEM python, which has no fastapi.
    A deliverable whose own interface is untested is how that hides.
    """
    out = tmp_path / "out"
    proc = subprocess.run(
        [str(_RUN), _CASE["id"],
         "--index", str(_index(tmp_path)), "--out", str(out)],
        capture_output=True, text=True, timeout=300, cwd=str(_REPO),
    )

    assert proc.returncode == 0, (
        f"the documented command does not run\n{proc.stdout[-2000:]}\n"
        f"{proc.stderr[-2000:]}")
    assert (out / f"{_CASE['id']}.png").exists()


def test_an_unknown_case_id_fails_loudly(tmp_path):
    """Naming a case that is not in the index must not look like a pass."""
    proc = subprocess.run(
        [sys.executable, str(_RUN), "no-such-case",
         "--index", str(_index(tmp_path)), "--out", str(tmp_path / "out")],
        capture_output=True, text=True, timeout=300, cwd=str(_REPO),
    )

    assert proc.returncode != 0
    assert "no-such-case" in (proc.stdout + proc.stderr)
