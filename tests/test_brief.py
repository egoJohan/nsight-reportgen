from nsight.brief import parse_brief, Brief, SlideJob

SAMPLE = """# Attendo brief

Some intro prose.

```slide
id: aided_awareness
slide_idx: 14
metric: aided_awareness
segment: kaikki
title: Autettu tunnettuus
chart:
  name: Content Placeholder 9
  series_name: Marraskuu 2025
key_message:
  name: Text Placeholder 5
```

Trailing prose.
"""


def test_parse_brief(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text(SAMPLE, encoding="utf-8")
    brief = parse_brief(path)
    assert isinstance(brief, Brief)
    assert len(brief.jobs) == 1
    job = brief.jobs[0]
    assert isinstance(job, SlideJob)
    assert job.id == "aided_awareness"
    assert job.slide_idx == 14
    assert isinstance(job.slide_idx, int)
    assert job.metric == "aided_awareness"
    assert job.segment == "kaikki"
    assert job.title == "Autettu tunnettuus"
    assert job.chart["name"] == "Content Placeholder 9"
    assert job.chart["series_name"] == "Marraskuu 2025"
    assert job.key_message["name"] == "Text Placeholder 5"
    assert job.table is None
    assert job.raw["id"] == "aided_awareness"


def test_parse_brief_defaults(tmp_path):
    text = """```slide
id: x
slide_idx: 3
metric: aided_awareness
```"""
    path = tmp_path / "b.md"
    path.write_text(text, encoding="utf-8")
    job = parse_brief(path).jobs[0]
    assert job.segment == "kaikki"
    assert job.title is None
    assert job.chart is None
    assert job.key_message is None
