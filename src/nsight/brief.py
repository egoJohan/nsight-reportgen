"""Brief parser: a Markdown file with one ```slide YAML block per job."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_BLOCK_RE = re.compile(r"```slide\n(.*?)```", re.S)


@dataclass
class SlideJob:
    id: str
    slide_idx: int
    metric: str
    segment: str = "kaikki"
    title: str | None = None
    chart: dict | None = None
    table: dict | None = None
    key_message: dict | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class Brief:
    jobs: list[SlideJob] = field(default_factory=list)


def parse_brief(path: str | Path) -> Brief:
    text = Path(path).read_text(encoding="utf-8")
    jobs: list[SlideJob] = []
    for block in _BLOCK_RE.findall(text):
        raw = yaml.safe_load(block) or {}
        jobs.append(
            SlideJob(
                id=raw["id"],
                slide_idx=int(raw["slide_idx"]),
                metric=raw["metric"],
                segment=raw.get("segment", "kaikki"),
                title=raw.get("title"),
                chart=raw.get("chart"),
                table=raw.get("table"),
                key_message=raw.get("key_message"),
                raw=raw,
            )
        )
    return Brief(jobs=jobs)
