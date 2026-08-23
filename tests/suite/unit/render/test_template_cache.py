"""The template is resolved once per file, not once per slide.

Resolving a template used to cost a full `.pptx` parse plus a font measurement,
and both ran per slide: a 60-slide deck paid for all of it 60 times, which is
most of why opening a report felt like the machine had stopped answering.
"""
from __future__ import annotations

import shutil

from pptx import Presentation
from pptx.util import Inches

from reportbuilder.render import template_cache
from reportbuilder.render.default_template import build_default_template


def _a_template(tmp_path) -> str:
    """The house template — always available, no fixture file to ship."""
    return build_default_template(str(tmp_path / "a.pptx"))


def _another_template(tmp_path) -> str:
    """A genuinely different file: same builder, a different page size."""
    src = build_default_template(str(tmp_path / "b-src.pptx"))
    prs = Presentation(src)
    prs.slide_width = Inches(12)
    out = str(tmp_path / "b.pptx")
    prs.save(out)
    return out


def test_resolve_returns_the_same_object_for_the_same_file(tmp_path):
    src = tmp_path / "t.pptx"
    shutil.copy(_a_template(tmp_path), src)
    assert template_cache.resolve(str(src)) is template_cache.resolve(str(src))


def test_resolve_re_reads_a_changed_file(tmp_path):
    """A re-uploaded template must not keep serving the old resolution."""
    src = tmp_path / "t.pptx"
    shutil.copy(_a_template(tmp_path), src)
    first = template_cache.resolve(str(src))
    shutil.copy(_another_template(tmp_path), src)
    assert template_cache.resolve(str(src)) is not first


def test_style_matches_load_style_spec(tmp_path):
    from reportbuilder.render.style_spec import load_style_spec

    src = tmp_path / "t.pptx"
    shutil.copy(_a_template(tmp_path), src)
    assert (template_cache.resolve(str(src)).style.chart_layout_index
            == load_style_spec(str(src)).chart_layout_index)


def test_the_spec_is_built_once_and_carries_a_title_size(tmp_path):
    """The whole point: type sizes are decided per TEMPLATE, before any slide."""
    src = tmp_path / "t.pptx"
    shutil.copy(_a_template(tmp_path), src)
    spec = template_cache.resolve(str(src)).spec
    assert spec.title.size_pt > 0
    assert spec.subtitle.size_pt > 0
    assert spec.background


def test_the_spec_travels_with_the_style(tmp_path):
    """slide_chrome is handed a style, not a ResolvedTemplate, and must still read it."""
    src = tmp_path / "t.pptx"
    shutil.copy(_a_template(tmp_path), src)
    resolved = template_cache.resolve(str(src))
    assert resolved.style.resolved_spec is resolved.spec


def test_the_template_is_parsed_once_for_a_whole_deck(tmp_path, monkeypatch):
    """Sixty slides, one parse — the regression this module exists to prevent."""
    import reportbuilder.render.template_cache as tc

    src = tmp_path / "t.pptx"
    shutil.copy(_a_template(tmp_path), src)
    tc._resolve.cache_clear()

    calls: list[str] = []
    real = tc.load_style_spec
    monkeypatch.setattr(tc, "load_style_spec",
                        lambda p: (calls.append(p), real(p))[1])

    for _ in range(60):
        tc.resolve(str(src))
    assert len(calls) == 1
