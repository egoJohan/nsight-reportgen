"""Two independent questions about a domain, stored in two places.

"Who may sign in without an invitation" and "what may they do" used to be one
list: a domain carried a mode, and the mode was the access. They are not the
same question. A partner whose people are all invited by hand can still be
owed access to everything; a contractor domain may be allowed to sign itself
in and be owed nothing. So `allowed_domains` answers admission and
`domain_access` answers permission, and a domain may appear in either, both,
or neither. (Johan, 2026-09-11)

The shapes written before this split are still read: a bare string admits and
grants nothing, and a `{domain, mode}` entry left in `allowed_domains` does
both, which is what it meant when it was written.
"""
from __future__ import annotations

from reportbuilder.auth.identity import (
    admitted_domains, domain_grants, domain_modes, tenant_grant)
from reportbuilder.auth.permissions import ALL_SCOPE


class TestAdmission:
    def test_a_listed_domain_may_sign_in(self):
        assert admitted_domains({"allowed_domains": ["nsight.fi"]}) == frozenset({"nsight.fi"})

    def test_domains_are_matched_lower_case_and_trimmed(self):
        assert admitted_domains({"allowed_domains": ["  NSight.FI "]}) == \
            frozenset({"nsight.fi"})

    def test_being_granted_access_does_not_admit(self):
        """The point of the split: access is not a way in. Someone on this
        domain still needs an invitation to get an account at all."""
        assert admitted_domains(
            {"domain_access": [{"domain": "partner.com", "mode": "edit"}]}) == frozenset()

    def test_blank_and_malformed_entries_are_dropped(self):
        assert admitted_domains({"allowed_domains": ["", "  ", None, 42]}) == frozenset()

    def test_nothing_configured_admits_nobody(self):
        assert admitted_domains({}) == frozenset()


class TestAccess:
    def test_a_domain_carries_a_mode(self):
        assert domain_modes({"domain_access": [{"domain": "nsight.fi", "mode": "edit"}]}) == \
            {"nsight.fi": "edit"}

    def test_being_allowed_to_sign_in_grants_nothing(self):
        """The other half of the split, and the safe half: a deployment that
        only ever listed domains to let people in must not have handed those
        people every customer the moment this shipped."""
        assert domain_modes({"allowed_domains": ["nsight.fi"]}) == {}

    def test_an_unknown_mode_falls_back_to_view(self):
        """The safer of the two. A typo must not hand out write access."""
        assert domain_modes({"domain_access": [{"domain": "x.fi", "mode": "Edit"}]}) == \
            {"x.fi": "view"}
        assert domain_modes({"domain_access": [{"domain": "x.fi", "mode": "owner"}]}) == \
            {"x.fi": "view"}

    def test_an_entry_with_no_mode_is_not_access(self):
        assert domain_modes({"domain_access": [{"domain": "x.fi"}]}) == {}

    def test_a_mode_left_in_the_sign_in_list_is_still_honoured(self):
        """Written by the screen that had one list. It meant admit AND grant,
        so it keeps meaning that -- upgrading must not quietly drop access
        somebody is relying on."""
        stored = {"allowed_domains": [{"domain": "nsight.fi", "mode": "edit"}]}
        assert domain_modes(stored) == {"nsight.fi": "edit"}
        assert admitted_domains(stored) == frozenset({"nsight.fi"})

    def test_the_dedicated_list_wins_over_a_leftover_mode(self):
        stored = {"allowed_domains": [{"domain": "nsight.fi", "mode": "edit"}],
                  "domain_access": [{"domain": "nsight.fi", "mode": "view"}]}
        assert domain_modes(stored) == {"nsight.fi": "view"}


class TestTenantGrant:
    def test_the_grant_follows_the_access_list(self):
        g = tenant_grant("a@nsight.fi",
                         {"domain_access": [{"domain": "nsight.fi", "mode": "edit"}]})
        assert (g.scope, g.mode) == (ALL_SCOPE, "edit")

    def test_a_domain_granted_nothing_gets_no_grant(self):
        assert tenant_grant("a@nsight.fi", {"allowed_domains": ["nsight.fi"]}) is None

    def test_another_domain_gets_no_grant(self):
        assert tenant_grant("a@elsewhere.com",
                            {"domain_access": [{"domain": "nsight.fi", "mode": "edit"}]}) is None


class TestSignUpGrants:
    def test_an_unlisted_domain_may_not_sign_itself_in(self):
        """None, not (), is the "no account for you" answer."""
        assert domain_grants("a@elsewhere.com", {"allowed_domains": ["nsight.fi"]}) is None

    def test_an_admitted_domain_starts_with_nothing_of_its_own(self):
        """The tenant grant is read from the setting on every request (see
        test_tenant_grant_is_live.py), never stamped onto the new account."""
        assert domain_grants("a@nsight.fi", {
            "allowed_domains": ["nsight.fi"],
            "domain_access": [{"domain": "nsight.fi", "mode": "edit"}]}) == ()

    def test_the_older_default_grants_still_ride_along(self):
        """Anyone relying on named default grants keeps them on the new
        account, rather than having them silently dropped."""
        grants = domain_grants("a@nsight.fi", {
            "allowed_domains": ["nsight.fi"],
            "default_grants": [{"scope": "cust-abc", "mode": "edit"}]})
        assert [(g.scope, g.mode) for g in grants] == [("cust-abc", "edit")]
