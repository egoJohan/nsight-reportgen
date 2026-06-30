"""A0 curation tests — metadata filter (REQ-C-05) and var<N>O<M> grouping (REQ-M-02).

Unit tests operate on small synthetic models / SAV files (no real .sav required).
The @pytest.mark.integration test validates against the real Attendo .sav.
"""
from __future__ import annotations

import pandas as pd
import pyreadstat
import pytest

from reportbuilder.ingest.sav_reader import read_sav, _is_metadata, _is_unlabeled_helper
from reportbuilder.ingest.multi_group import (
    suggest_multi_groups,
    apply_groups,
    _group_text,
    _shared_question,
)
from reportbuilder.model.question import QuestionModel, Question, Variable, ValueLabel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def curation_sav(tmp_path):
    """Synthetic SAV with metadata vars, a real question, and an O-pattern family."""
    df = pd.DataFrame({
        "Vip":     [1.0, 2.0, 3.0],
        "var4":    [10.0, 20.0, 30.0],
        "q1":      [1.0, 2.0, 3.0],
        "var10O1": [1.0, 0.0, 1.0],
        "var10O2": [0.0, 1.0, 0.0],
        "var10O3": [1.0, 1.0, 0.0],
    })
    path = tmp_path / "curation.sav"
    pyreadstat.write_sav(
        df, str(path),
        column_labels={
            "Vip":     "IP Address",
            "var4":    "pid",
            "q1":      "Overall satisfaction",
            "var10O1": "Attendo:What brand do you know?",
            "var10O2": "Esperi:What brand do you know?",
            "var10O3": "Mainio:What brand do you know?",
        },
        variable_value_labels={
            "var10O1": {0: "Unchecked", 1: "Checked"},
            "var10O2": {0: "Unchecked", 1: "Checked"},
            "var10O3": {0: "Unchecked", 1: "Checked"},
        },
    )
    return str(path)


# ---------------------------------------------------------------------------
# Helper: build a QuestionModel from plain dicts (no SAV I/O)
# ---------------------------------------------------------------------------

def _var(name: str, label: str, binary: bool = False) -> Variable:
    vls = (ValueLabel(0.0, "No"), ValueLabel(1.0, "Yes")) if binary else ()
    return Variable(
        name=name,
        label=label,
        measurement="categorical",
        value_labels=vls,
        missing_values=frozenset(),
    )


def _model(*vars_: Variable) -> QuestionModel:
    return QuestionModel(
        variables={v.name: v for v in vars_},
        questions=[
            Question(qid=v.name.lower(), kind="single", variables=(v.name,), text=v.label)
            for v in vars_
        ],
    )


# ---------------------------------------------------------------------------
# A0.1 — Metadata filter: _is_metadata heuristic
# ---------------------------------------------------------------------------

class TestIsMetadata:
    """REQ-C-05: survey-platform metadata detection."""

    def test_known_name_vip(self):
        assert _is_metadata("Vip", "IP Address") is True

    def test_known_name_vrid(self):
        assert _is_metadata("vrid", "Response ID") is True

    def test_known_name_vstatus(self):
        assert _is_metadata("Vstatus", "Status") is True

    def test_known_name_vsessionid(self):
        assert _is_metadata("Vsessionid", "SessionID") is True

    def test_pid_by_exact_label(self):
        """var4 has label 'pid' — detected by exact label match."""
        assert _is_metadata("var4", "pid") is True

    def test_psid_by_exact_label(self):
        assert _is_metadata("var5", "psid") is True

    def test_real_question_not_metadata(self):
        """A genuine survey question must NOT be filtered."""
        assert _is_metadata("q1", "Overall satisfaction") is False

    def test_employment_status_not_metadata(self):
        """'Employment Status' must NOT match the bare 'status' pattern."""
        assert _is_metadata("q_status", "Employment Status") is False

    def test_case_insensitive_name(self):
        assert _is_metadata("VIP", "Whatever") is True

    # --- survey-engine paradata with varying suffixes (label prefixes) ---

    def test_survey_timer_label(self):
        assert _is_metadata("var128", "Survey timer") is True

    def test_answer_count_label(self):
        assert _is_metadata("var145", "answer count") is True

    def test_hidden_value_label_prefix(self):
        """'Hidden value: <varying text>' is a platform hidden field."""
        assert _is_metadata("var149", "Hidden value: joku muu mikä vastaajat") is True

    def test_new_percent_branch_label(self):
        assert _is_metadata("var129", "New Percent Branch - Concept") is True

    def test_url_capture_label_prefix(self):
        """Labels like 'URL_profiili' / 'URL_Region' are URL query-string captures."""
        assert _is_metadata("var18", "URL_profiili") is True
        assert _is_metadata("var130", "URL_Region") is True

    def test_link_name_label(self):
        assert _is_metadata("LinkName", "Link Name") is True

    # --- platform recode columns by variable name ---

    def test_url_name_prefix(self):
        """URL-derived recodes (label == name) caught by the 'url' name prefix."""
        assert _is_metadata("URLprofiilinew", "URLprofiilinew") is True
        assert _is_metadata("URL_Villas_numeric", "URL_Villas_numeric") is True

    def test_branch_numeric_name(self):
        assert _is_metadata("Branch_numeric", "Branch_numeric") is True

    def test_q_nchoices_name(self):
        assert _is_metadata("Q_nchoices", "Q_nchoices") is True

    # --- analyst segmentation variables must NOT be dropped (like Inhimilli) ---

    def test_segment_vieralijat_kept(self):
        assert _is_metadata("vieralijat", "vieralijat") is False

    def test_segment_contracts_kept(self):
        assert _is_metadata("contracts_1", "contracts_1") is False

    def test_segment_owner_flags_kept(self):
        assert _is_metadata("VillastaiGold", "VillastaiGold") is False
        assert _is_metadata("Perusomistajat", "Perusomistajat") is False

    def test_question_mentioning_url_kept(self):
        """A real question that merely mentions a URL must survive (prefix, not substring)."""
        assert _is_metadata("var50", "Kuinka usein käytät verkkosivun URL-osoitetta?") is False


# ---------------------------------------------------------------------------
# Unlabeled categorical helper flags (segments) — excluded from questions,
# kept as classifying variables. Scale aggregates (Inhimilli) are NOT matched.
# ---------------------------------------------------------------------------

class TestUnlabeledHelper:
    def test_unlabeled_categorical_flag_is_helper(self):
        """label == name, no value labels, categorical → segmentation helper."""
        v = _var("vieralijat", "vieralijat")  # categorical, no value labels
        assert _is_unlabeled_helper("vieralijat", v) is True

    def test_unlabeled_binary_segment_is_helper(self):
        v = _var("Perusomistajat", "Perusomistajat")
        assert _is_unlabeled_helper("Perusomistajat", v) is True

    def test_scale_aggregate_is_helper(self):
        """A derived RATING aggregate (Inhimilli: scale, label==name, no value
        labels) is an analyst working column that just duplicates a battery's
        statements → helper (excluded from the question browser, kept as a
        variable)."""
        v = Variable(
            name="Inhimilli",
            label="Inhimilli",
            measurement="scale",
            value_labels=(),
            missing_values=frozenset(),
        )
        assert _is_unlabeled_helper("Inhimilli", v) is True

    def test_labelled_scale_var_is_not_helper(self):
        """A scale variable WITH a real descriptive label is a real question."""
        v = Variable(
            name="q12",
            label="How satisfied are you overall?",
            measurement="scale",
            value_labels=(),
            missing_values=frozenset(),
        )
        assert _is_unlabeled_helper("q12", v) is False

    def test_value_labelled_var_is_not_helper(self):
        """A coded categorical WITH value labels is a real question, not a helper."""
        v = _var("q1", "q1", binary=True)  # has Yes/No value labels
        assert _is_unlabeled_helper("q1", v) is False

    def test_labelled_question_is_not_helper(self):
        """A categorical with a human label (≠ name) is a real question."""
        v = _var("var3", "Minkä ikäinen olet?")
        assert _is_unlabeled_helper("var3", v) is False

    def test_text_var_is_not_helper(self):
        v = Variable(
            name="var7",
            label="var7",
            measurement="text",
            value_labels=(),
            missing_values=frozenset(),
        )
        assert _is_unlabeled_helper("var7", v) is False


# ---------------------------------------------------------------------------
# A0.1 — Metadata filter via read_sav
# ---------------------------------------------------------------------------

class TestMetadataFilterInReadSav:
    """REQ-C-05: metadata vars excluded from questions, kept in variables."""

    def test_metadata_excluded_from_questions(self, curation_sav):
        """Vip and var4 (pid) must NOT appear in the questions list."""
        _, model = read_sav(curation_sav)
        q_var_names = {q.variables[0] for q in model.questions if q.kind == "single"}
        assert "Vip" not in q_var_names
        assert "var4" not in q_var_names

    def test_metadata_kept_in_variables(self, curation_sav):
        """Even though excluded from questions, metadata vars must remain in variables."""
        _, model = read_sav(curation_sav)
        assert "Vip" in model.variables
        assert "var4" in model.variables

    def test_real_question_stays_in_questions(self, curation_sav):
        """q1 (Overall satisfaction) must appear as a question."""
        _, model = read_sav(curation_sav)
        q_var_names = {q.variables[0] for q in model.questions if q.kind == "single"}
        assert "q1" in q_var_names

    def test_question_count_excludes_metadata(self, curation_sav):
        """Metadata vars (Vip, var4) are filtered: 4 non-metadata cols → 4 questions."""
        _, model = read_sav(curation_sav)
        # SAV has 6 columns: Vip, var4, q1, var10O1, var10O2, var10O3
        # Metadata: Vip, var4 → 4 non-metadata questions
        assert len(model.questions) == 4

    def test_all_variables_still_present(self, curation_sav):
        """variables dict must contain all 6 columns from the SAV."""
        _, model = read_sav(curation_sav)
        assert len(model.variables) == 6


# ---------------------------------------------------------------------------
# A0.2 — var<N>O<M> option-family grouping
# ---------------------------------------------------------------------------

class TestOPatternGrouping:
    """REQ-M-02: var<N>O<M> families collapse into ONE multi question."""

    def test_o_pattern_family_creates_one_group(self):
        """var10O1, var10O2, var10O3 share stem var10 → grouped into one multi."""
        m = _model(
            _var("var10O1", "Attendo:Which brand?", binary=True),
            _var("var10O2", "Esperi:Which brand?", binary=True),
            _var("var10O3", "Mainio:Which brand?", binary=True),
        )
        groups = suggest_multi_groups(m)
        assert len(groups) == 1
        group = groups[0]
        assert set(group) == {"var10O1", "var10O2", "var10O3"}

    def test_o_pattern_family_becomes_single_multi_question(self):
        """apply_groups turns the O-family into exactly one multi Question."""
        m = _model(
            _var("var10O1", "Attendo:Which brand?", binary=True),
            _var("var10O2", "Esperi:Which brand?", binary=True),
            _var("var10O3", "Mainio:Which brand?", binary=True),
        )
        groups = suggest_multi_groups(m)
        m2 = apply_groups(m, groups)
        multi_qs = [q for q in m2.questions if q.kind == "multi"]
        assert len(multi_qs) == 1
        assert set(multi_qs[0].variables) == {"var10O1", "var10O2", "var10O3"}

    def test_o_pattern_multi_question_kind(self):
        m = _model(
            _var("var10O1", "A:Question?", binary=True),
            _var("var10O2", "B:Question?", binary=True),
        )
        groups = suggest_multi_groups(m)
        m2 = apply_groups(m, groups)
        assert m2.questions[0].kind == "multi"

    def test_singleton_o_pattern_not_grouped(self):
        """A single var10O1 with no siblings stays as a singleton."""
        m = _model(_var("var10O1", "Only:Solo?", binary=True))
        groups = suggest_multi_groups(m)
        assert groups == []

    def test_non_o_binary_vars_still_grouped_by_prefix(self):
        """Binary vars without O-pattern (names ending in digits) are grouped by prefix heuristic."""
        m = _model(
            _var("brand1", "Grid: Option A", binary=True),
            _var("brand2", "Grid: Option B", binary=True),
        )
        groups = suggest_multi_groups(m)
        # 'brand1' and 'brand2' share prefix 'brand' (strip trailing digit) → grouped
        assert len(groups) == 1
        assert set(groups[0]) == {"brand1", "brand2"}

    def test_o_pattern_grouping_via_read_sav(self, curation_sav):
        """Full pipeline: read_sav → suggest → apply collapses var10 into one multi."""
        _, model = read_sav(curation_sav)
        groups = suggest_multi_groups(model)
        model2 = apply_groups(model, groups)
        multi_qs = [q for q in model2.questions if q.kind == "multi"]
        assert len(multi_qs) == 1
        assert set(multi_qs[0].variables) == {"var10O1", "var10O2", "var10O3"}


# ---------------------------------------------------------------------------
# A0.3 — Brand:Question label split for group text (REQ-M-02)
# ---------------------------------------------------------------------------

class TestBrandQuestionText:
    """Brand:Question label pattern → shared right side becomes question text."""

    def test_brand_question_text_extracted(self):
        """'Brand:SharedQuestion' → text = 'SharedQuestion'."""
        m = _model(
            _var("var10O1", "Attendo:What brand do you know?"),
            _var("var10O2", "Esperi:What brand do you know?"),
            _var("var10O3", "Mainio:What brand do you know?"),
        )
        text = _group_text(m, ("var10O1", "var10O2", "var10O3"))
        assert text == "What brand do you know?"

    def test_brand_question_text_from_apply_groups(self):
        """apply_groups uses the Brand:Question text for the multi question."""
        m = _model(
            _var("var10O1", "Attendo:What brand do you know?", binary=True),
            _var("var10O2", "Esperi:What brand do you know?", binary=True),
        )
        groups = suggest_multi_groups(m)
        m2 = apply_groups(m, groups)
        multi_q = next(q for q in m2.questions if q.kind == "multi")
        assert multi_q.text == "What brand do you know?"

    def test_shared_question_identical(self):
        assert _shared_question(["A common question?", "A common question?"]) == (
            "A common question?"
        )

    def test_shared_question_truncated_prefixes(self):
        """SPSS truncates Option:Question per member → right sides are prefixes;
        the longest (most complete) is returned."""
        full = "Ohessa naet listauksen erilaisia omistajaetuja jotka on tarkoitettu"
        rights = [full[:40], full[:55], full[:67]]
        assert _shared_question(rights) == full[:67]

    def test_shared_question_unrelated_returns_none(self):
        assert _shared_question(["How old are you?", "Where do you live?"]) is None

    def test_truncated_option_question_splits(self):
        """A var<N>O<M> family whose Option:Question labels are truncated to
        different lengths still splits into one multi with options as labels."""
        q = (
            "Ohessa naet listauksen erilaisia omistajaetuja jotka on tarkoitettu "
            "oman Holiday Club lomaviikon omistajille valitse enintaan viisi"
        )
        m = _model(
            _var("var47O1", f"Omistajien lisaviikot:{q[:70]}", binary=True),
            _var("var47O2", f"Alennukset hotellikohteista pidempi optio:{q[:50]}", binary=True),
            _var("var47O3", f"Joku muu etu:{q[:62]}", binary=True),
        )
        groups = suggest_multi_groups(m)
        m2 = apply_groups(m, groups)
        mq = next(qq for qq in m2.questions if qq.kind == "multi")
        assert mq.text == q[:70]  # longest right side
        assert m2.variables["var47O1"].label == "Omistajien lisaviikot"
        assert m2.variables["var47O2"].label == "Alennukset hotellikohteista pidempi optio"

    def test_numeric_prefix_colon_pattern(self):
        """'1 :Question text' / '2 :Question text' → shared text extracted."""
        m = _model(
            _var("var17O1", "1 :Name all brands you know"),
            _var("var17O2", "2 :Name all brands you know"),
        )
        text = _group_text(m, ("var17O1", "var17O2"))
        assert text == "Name all brands you know"

    def test_fallback_to_prefix_when_right_sides_differ(self):
        """If right-hand sides differ, falls back to common prefix."""
        m = _model(
            _var("var10O1", "Q: First question"),
            _var("var10O2", "Q: Second question"),
        )
        text = _group_text(m, ("var10O1", "var10O2"))
        # Right sides differ → falls back to common prefix "Q"
        assert "Q" in text


# ---------------------------------------------------------------------------
# Integration test — real Attendo .sav
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_attendo_curation_metadata_excluded():
    """REQ-C-05: IP Address / Response ID / Status are NOT questions after read_sav."""
    from reportbuilder import config
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")

    _, model = read_sav(config.ATTENDO_SAV)
    q_var_names = {q.variables[0] for q in model.questions if q.kind == "single"}

    assert "Vip" not in q_var_names, "IP Address (Vip) must not be a question"
    assert "Vrid" not in q_var_names, "Response ID (Vrid) must not be a question"
    assert "Vstatus" not in q_var_names, "Status (Vstatus) must not be a question"
    assert "var4" not in q_var_names, "pid (var4) must not be a question"
    assert "var5" not in q_var_names, "psid (var5) must not be a question"

    # All filtered variables must still be accessible in the variables dict
    for name in ("Vip", "Vrid", "Vstatus", "var4", "var5"):
        assert name in model.variables, f"{name} must remain in variables dict"


@pytest.mark.integration
def test_attendo_curation_var18_is_one_multi():
    """REQ-M-02: var18 aided-awareness (9 O-pattern vars) collapses into ONE multi question."""
    from reportbuilder import config
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")

    _, model = read_sav(config.ATTENDO_SAV)
    groups = suggest_multi_groups(model)
    model2 = apply_groups(model, groups)

    # var18O45..53 must all be in the same multi question
    var18_qs = [q for q in model2.questions if "var18O45" in q.variables]
    assert len(var18_qs) == 1, "var18 family must produce exactly one multi question"

    multi_q = var18_qs[0]
    assert multi_q.kind == "multi"

    expected_vars = {
        "var18O45", "var18O46", "var18O47", "var18O48", "var18O49",
        "var18O50", "var18O51", "var18O52", "var18O53",
    }
    assert set(multi_q.variables) == expected_vars, (
        f"All 9 aided-awareness vars must be in the multi question, got: {multi_q.variables}"
    )


@pytest.mark.integration
def test_attendo_curation_question_count_reduced():
    """REQ-C-05, REQ-M-02: curated question count is much smaller than raw 229."""
    from reportbuilder import config
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")

    _, model = read_sav(config.ATTENDO_SAV)
    groups = suggest_multi_groups(model)
    model2 = apply_groups(model, groups)

    count = len(model2.questions)
    assert count < 200, (
        f"Curated question count ({count}) should be much smaller than 229 "
        f"after filtering metadata and collapsing O-pattern families"
    )
    # Also confirm the variables dict is unchanged (all 229 still present)
    assert len(model2.variables) == 229


@pytest.mark.integration
def test_attendo_var18_question_text_is_shared_question():
    """The var18 multi question text is the shared right-hand side of the Brand:Question labels."""
    from reportbuilder import config
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")

    _, model = read_sav(config.ATTENDO_SAV)
    groups = suggest_multi_groups(model)
    model2 = apply_groups(model, groups)

    var18_q = next(q for q in model2.questions if "var18O45" in q.variables)
    # All var18 labels look like "Attendo:Mitä seuraavista..." → text = "Mitä seuraavista..."
    assert "Mitä seuraavista" in var18_q.text, (
        f"Expected shared question text, got: {var18_q.text!r}"
    )


# ---------------------------------------------------------------------------
# Curation corpus — verify ingest/curation across every real export (REQ-C-05).
# Each is skip-if-absent so the suite still runs without the (PII) SAVs present.
# ---------------------------------------------------------------------------

from reportbuilder.ingest.sav_reader import _is_metadata as _meta  # noqa: E402
from reportbuilder.ingest.multi_group import enrich_model  # noqa: E402


def _corpus_model(name: str):
    """Load + fully curate a corpus SAV by short name, or skip if absent."""
    from reportbuilder import config

    path = config.CORPUS_SAVS[name]
    if not path.exists():
        pytest.skip(f"{name} .sav not present")
    df, model = read_sav(path)
    return df, enrich_model(model)


@pytest.mark.integration
@pytest.mark.parametrize("name", ["attendo", "holidayclub", "synsam"])
def test_corpus_loads_and_has_questions(name):
    """Every corpus SAV ingests and yields a non-trivial curated question set."""
    _, model = _corpus_model(name)
    assert len(model.questions) > 5


@pytest.mark.integration
@pytest.mark.parametrize("name", ["attendo", "holidayclub", "synsam"])
def test_corpus_no_metadata_leaks_into_questions(name):
    """No survey-platform metadata/paradata variable survives as a question."""
    _, model = _corpus_model(name)
    leaked = [
        q.variables[0]
        for q in model.questions
        if q.kind == "single" and _meta(q.variables[0], q.text or q.variables[0])
    ]
    assert not leaked, f"{name}: metadata leaked into questions: {leaked}"


@pytest.mark.integration
def test_holidayclub_paradata_and_segments_excluded():
    """Holiday Club: paradata (Survey timer, answer count, Hidden value, URL
    captures) and unlabeled segment flags are NOT questions; the segments remain
    available as classifying variables (kept in the variables dict)."""
    _, model = _corpus_model("holidayclub")
    q_texts = {(q.text or "") for q in model.questions}

    for bad in ("Survey timer", "answer count", "Hidden value", "URL_profiili"):
        assert not any(bad.lower() in t.lower() for t in q_texts), (
            f"paradata '{bad}' must not be a question"
        )

    segments = ["vieralijat", "contracts_1", "VillastaiGold", "Perusomistajat"]
    q_vars = {q.variables[0] for q in model.questions if q.kind == "single"}
    for seg in segments:
        assert seg not in q_vars, f"segment '{seg}' must not be a question"
        assert seg in model.variables, (
            f"segment '{seg}' must stay available as a classifying variable"
        )


@pytest.mark.integration
def test_attendo_unlabeled_recodes_excluded_from_questions_kept_as_variables():
    """Attendo: derived recodes — both RATING aggregates (Inhimilli, Luotettava:
    scale, label==name) and unlabeled nominal flags (Kokemusta) — are excluded
    from the question browser (they just duplicate the rating battery / are
    working columns) but remain in the variables dict for use as classifying /
    combo-secondary variables."""
    _, model = _corpus_model("attendo")
    q_vars = {q.variables[0] for q in model.questions if q.kind == "single"}

    for nm in ("Inhimilli", "Luotettava", "Kokemusta"):
        assert nm not in q_vars, f"derived recode '{nm}' must not be a question"
        assert nm in model.variables, f"'{nm}' must stay available as a variable"
