"""One tenant, one deny list — so it must hold EVERY study's terms.

datahive keeps a single policy per tenant: `/api/v1/llm/ask` resolves it with
`workspace_uuid=None` and its request model has no workspace to scope by, so a
per-study deny list could never apply to prose. Registration replaces the whole
list, and nSight was registering only the study being accepted.

Measured on staging, 2026-09-09: a study accepted 14 real brand names on the
8th at 15:44; the next morning at 05:48 a different study accepted none, and
that PUT left the tenant policy empty. Thirteen studies showed terms accepted
in the UI and datahive was masking on nothing.

Nothing downstream could notice, either — `/llm/ask` answers
`pseudonymized: true` whenever its pseudonymiser ran, including when the deny
list is empty, so `masked_chat`'s assertion passes while the protection is
absent. Hence the union here, the read-back in `register_sensitive_terms`, and
the per-study check on the AI routes. (Johan, 2026-09-09)
"""
from __future__ import annotations

import pytest

from reportbuilder.api.routes_questions import _tenant_terms


class _Client:
    """The stored acceptances of a tenant, as the route sees them."""

    def __init__(self, by_material: dict[str, list[str]]):
        self._by = by_material

    def sensitive_terms(self, material_id):
        return {"accepted": self._by.get(material_id)}

    def all_accepted_terms(self, *, exclude=""):
        seen = {}
        for mid, terms in self._by.items():
            if exclude and mid == exclude:
                continue
            for t in terms or []:
                seen[t] = None
        return sorted(seen, key=lambda t: (-len(t), t.lower()))


def test_accepting_one_study_keeps_every_other_studys_terms():
    client = _Client({"mat-validia": ["Attendo", "Esperi Care", "Humana Suomi"],
                      "mat-tyo": []})

    # the study that had none accepts none again — the exact 05:48 event
    registered = _tenant_terms(client, "mat-tyo", [])

    assert set(registered) == {"Attendo", "Esperi Care", "Humana Suomi"}, (
        "another study's acceptance wiped the tenant's protection")


def test_a_studys_own_list_is_replaced_not_added_to():
    """Within ONE study the accepted list is the whole truth: a term removed
    there must stop being registered on its behalf."""
    client = _Client({"mat-a": ["Vanha", "Pysyy"]})

    registered = _tenant_terms(client, "mat-a", ["Pysyy"])

    assert "Vanha" not in registered
    assert "Pysyy" in registered


def test_a_term_another_study_still_accepts_survives_its_removal():
    client = _Client({"mat-a": ["Attendo"], "mat-b": ["Attendo", "Esperi"]})

    registered = _tenant_terms(client, "mat-a", [])

    assert "Attendo" in registered, "still accepted by another study"
    assert "Esperi" in registered


def test_longest_first_so_a_prefix_never_eats_a_longer_name():
    client = _Client({"mat-a": ["Esperi", "Esperi Care Oy"]})
    registered = _tenant_terms(client, "mat-a", ["Esperi", "Esperi Care Oy"])
    assert registered.index("Esperi Care Oy") < registered.index("Esperi")


def test_a_store_failure_fails_the_acceptance():
    """Silently narrowing the list is the failure this exists to prevent."""
    class _Broken(_Client):
        def all_accepted_terms(self, *, exclude=""):
            raise RuntimeError("store unreachable")

    with pytest.raises(RuntimeError):
        _tenant_terms(_Broken({"mat-a": ["Attendo"]}), "mat-a", ["Attendo"])
