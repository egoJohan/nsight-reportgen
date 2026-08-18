"""Path grammar (design §4/§6). These paths are the permission unit, so the
tests care most about what a malformed segment could do to a grant scope."""
import pytest

from reportbuilder.store import paths as P


class TestGrammar:
    def test_report_lives_under_its_case(self):
        assert P.report_path("acme", "case-1", "rep-9") == "acme/case-1/report/rep-9"

    def test_material_and_its_config_are_siblings(self):
        m = P.material_path("acme", "case-1", "mat-2")
        assert m == "acme/case-1/material/mat-2"
        assert P.material_config_path("acme", "case-1", "mat-2") == m + ".config"

    def test_template_hangs_off_the_customer_not_a_case(self):
        # Presentaatiopohjat binds per asiakas/case/report, lowest wins, so a
        # template must outlive any single case.
        assert P.template_path("acme", "tpl-1") == "acme/template/tpl-1"

    def test_settings_are_global(self):
        assert P.settings_path("branding") == "settings/branding"


class TestGrantScopes:
    """The prefixes are what a token gets caveated to (P-O-05, P-O-06/07)."""

    def test_customer_prefix_covers_every_case_of_that_customer(self):
        pre = P.customer_prefix("acme")
        assert P.report_path("acme", "case-1", "r").startswith(pre)
        assert P.report_path("acme", "case-2", "r").startswith(pre)
        assert P.template_path("acme", "t").startswith(pre)

    def test_customer_prefix_excludes_other_customers(self):
        assert not P.report_path("other", "case-1", "r").startswith(P.customer_prefix("acme"))

    def test_case_prefix_covers_one_case_only(self):
        pre = P.case_prefix("acme", "case-1")
        assert P.report_path("acme", "case-1", "r").startswith(pre)
        assert P.material_path("acme", "case-1", "m").startswith(pre)
        assert not P.report_path("acme", "case-2", "r").startswith(pre)

    def test_a_customer_prefix_is_not_a_prefix_of_a_similarly_named_one(self):
        # "acme/" must not match "acme-corp/..." — without the trailing slash a
        # grant on one customer would silently cover another.
        assert not "acme-corp/case-1/report/r".startswith(P.customer_prefix("acme"))


class TestSegmentValidation:
    @pytest.mark.parametrize("bad", ["", "   ", None, 123])
    def test_empty_or_non_string_segments_are_refused(self, bad):
        with pytest.raises(P.PathError):
            P.report_path("acme", "case-1", bad)

    def test_a_slash_cannot_be_smuggled_into_a_segment(self):
        # This is the one that matters: "../other" or "x/y" would re-parent the
        # object into a different grant scope.
        with pytest.raises(P.PathError):
            P.report_path("acme", "case-1", "x/y")
        with pytest.raises(P.PathError):
            P.report_path("acme", "../other", "r")

    @pytest.mark.parametrize("bad", [".", ".."])
    def test_relative_segments_are_refused(self, bad):
        with pytest.raises(P.PathError):
            P.material_path("acme", bad, "m")

    def test_surrounding_whitespace_is_trimmed_not_rejected(self):
        assert P.report_path(" acme ", "case-1", "r") == "acme/case-1/report/r"


class TestLabels:
    def test_labels_share_the_nsight_root(self):
        # Hierarchical labels: "nsight:report" stores ["nsight", "nsight:report"],
        # so ?label=nsight returns everything nSight owns.
        for lbl in (P.LABEL_REPORT, P.LABEL_MATERIAL, P.LABEL_CONFIG,
                    P.LABEL_TEMPLATE, P.LABEL_SETTINGS):
            assert lbl.startswith(P.LABEL_ROOT + ":")
