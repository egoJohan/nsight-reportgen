"""Both Erisan exports must offer a working path classifier, by whichever encoding
they happen to use, and both encodings must give the SAME answer.

Skipped when the client materials are absent (gitignored IPR).
(spec 2026-08-02 §4)
"""
from __future__ import annotations

import dataclasses
import pathlib

import pandas as pd
import pytest

from reportbuilder.api.model_loader import df_model_for_material
from reportbuilder.ingest.multi_group import member_masks, near_partition
from reportbuilder.ingest.sav_reader import string_categories
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine
from reportbuilder.store.memory_client import InMemoryDataHiveClient

_STORE = pathlib.Path("work/demo-store")


def _load(mid):
    if not (_STORE / "materials" / f"{mid}.sav").exists():
        pytest.skip(f"{mid} not available locally")
    return df_model_for_material(mid, InMemoryDataHiveClient(storage_dir=str(_STORE)))


def _banner_qids(df, model):
    out = []
    for q in model.questions:
        if q.kind != "multi":
            continue
        masks = member_masks(df, q.variables)
        if masks and near_partition(masks, len(df)):
            out.append(q.qid)
    return out


@pytest.mark.parametrize("mid", ["mat-erisan", "mat-erisan2"])
def test_export_offers_a_path_classifier(mid):
    df, model = _load(mid)
    string_ok = model.variables["var214"].measurement == "categorical"
    banner_ok = bool(_banner_qids(df, model))
    assert string_ok or banner_ok, f"{mid} offers no path classifier"


@pytest.mark.parametrize("mid", ["mat-erisan", "mat-erisan2"])
def test_var214_is_a_two_value_categorical(mid):
    df, _model = _load(mid)
    assert string_categories(df["var214"]) == ("Pakkausilme 1", "Pakkausilme 2")


def test_both_exports_agree_on_the_model():
    """The correctness property §2.2 exists to guarantee: the two exports differ
    only in whether the indicator columns carry value labels, and must not behave
    differently."""
    d1, m1 = _load("mat-erisan")
    d2, m2 = _load("mat-erisan2")
    assert m1.variables["var214"].measurement == m2.variables["var214"].measurement
    assert _banner_qids(d1, m1) == _banner_qids(d2, m2) == ["polku"]
    q1 = next(q for q in m1.questions if q.qid == "polku")
    q2 = next(q for q in m2.questions if q.qid == "polku")
    assert q1.variables == q2.variables
    assert q1.text == q2.text == "Polku"


def _first_single(model):
    for q in model.questions:
        if q.kind != "single":
            continue
        var = model.variables[q.variables[0]]
        if 2 <= len(var.value_labels) <= 8 and var.name != "var214":
            return q
    pytest.skip("no suitable single question")


def _spec(qid, clf):
    return ChartSpec(question_ref=qid, chart_type="horizontal_bar", statistic="pct",
                     classifying_var=clf, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s",
                     elements=ElementToggles())


def test_the_two_encodings_give_identical_numbers():
    """var214 (string) and polku (indicator columns) describe the same split, so a
    chart classified by either must agree cell for cell."""
    df, model = _load("mat-erisan")
    q = _first_single(model)
    by_string = engine.compute(q, _spec(q.qid, "var214"), df, model)
    by_banner = engine.compute(q, _spec(q.qid, "polku"), df, model)

    # segment names differ by encoding; compare positionally, Total last in both
    s_str = [s for s in by_string.segments if s != "Total"]
    s_ban = [s for s in by_banner.segments if s != "Total"]
    assert len(s_str) == len(s_ban) == 2
    assert by_string.base_n["Total"] == by_banner.base_n["Total"]
    for a, b in zip(s_str, s_ban):
        assert by_string.base_n[a] == by_banner.base_n[b], f"{a} vs {b}"
        for cat in by_string.categories:
            pa = by_string.cell(cat, a).pct
            pb = by_banner.cell(cat, b).pct
            assert pa == pytest.approx(pb, abs=0.05), f"{cat}: {a}={pa} {b}={pb}"


def test_the_split_matches_the_known_path_sizes():
    """255 / 256 — measured directly from the indicator columns."""
    df, model = _load("mat-erisan")
    q = _first_single(model)
    r = engine.compute(q, _spec(q.qid, "polku"), df, model)
    assert sorted(r.base_n[s] for s in r.segments if s != "Total") == [255, 256]


# ---- the grouping override must see the DATA everywhere a chart is computed ----
# suggest_indicator_families needs the DataFrame; without it the banner question
# never exists, so a chart classified by it silently renders unsplit. The picker
# (which uses model_loader) offered `polku` while the PREVIEW ignored it.

@pytest.mark.parametrize("loader", ["preview", "summary", "ai"])
def test_banner_question_exists_on_every_chart_computing_path(loader):
    """Each of these endpoints builds its own model; all must resolve `polku`."""
    from reportbuilder.ingest.grouping_override import apply_grouping_override
    from reportbuilder.ingest.sav_reader import read_sav

    path = _STORE / "materials" / "mat-erisan.sav"
    if not path.exists():
        pytest.skip("mat-erisan not available locally")
    df, model = read_sav(str(path))
    # every such path has the DataFrame in hand and must pass it
    m = apply_grouping_override(model, {}, df=df)
    assert any(q.qid == "polku" and q.kind == "multi" for q in m.questions), loader


def test_without_the_dataframe_the_banner_question_is_absent():
    """Documents WHY the df must be threaded — the failure is silent."""
    from reportbuilder.ingest.grouping_override import apply_grouping_override
    from reportbuilder.ingest.sav_reader import read_sav

    path = _STORE / "materials" / "mat-erisan.sav"
    if not path.exists():
        pytest.skip("mat-erisan not available locally")
    _df, model = read_sav(str(path))
    m = apply_grouping_override(model, {}, df=None)
    assert not any(q.qid == "polku" for q in m.questions)
