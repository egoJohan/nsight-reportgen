"""The path grammar: where an nSight object lives in datahive.

Path carries HIERARCHY, labels carry TYPE (design
`docs/superpowers/specs/2026-08-17-datahive-api-contract.md` §4/§6):

    {asiakas}/{case}/report/{report_id}              nsight:report
    {asiakas}/{case}/material/{material_id}          nsight:material
    {asiakas}/{case}/material/{material_id}.config   nsight:config
    {asiakas}/template/{template_id}                 nsight:template
    settings/{key}                                   nsight:settings

Why both axes: prefix listing scopes to a subtree server-side, and a label
answers "what is this" across subtrees. Keeping type OUT of the path matters
because renaming a path physically moves the object in datahive — with the type
in a label, a mis-shaped path is recoverable by relabelling rather than by
moving data.

The same path is the permission unit: a token caveated to `{asiakas}/**` grants
that customer, `{asiakas}/{case}/**` grants a single case (Speksi 2 P-O-05..07).
So these builders are the ONE place a path is spelled — an ad-hoc f-string
elsewhere is a permission bug waiting to happen.
"""
from __future__ import annotations

# Label vocabulary. Hierarchical: writing "nsight:report" stores
# ["nsight", "nsight:report"], so ?label=nsight matches everything we own.
LABEL_ROOT = "nsight"
LABEL_REPORT = "nsight:report"
LABEL_MATERIAL = "nsight:material"
LABEL_CONFIG = "nsight:config"
LABEL_TEMPLATE = "nsight:template"
LABEL_SETTINGS = "nsight:settings"

SETTINGS_ROOT = "settings"


class PathError(ValueError):
    """A path segment is missing or malformed."""


def _seg(value: str, what: str) -> str:
    """Validate one path segment.

    Segments are identifiers, not free text: a "/" would silently re-parent an
    object into another customer's subtree, which is also another customer's
    permission scope. Rejecting here is cheaper than auditing every call site.
    """
    if not isinstance(value, str) or not value.strip():
        raise PathError(f"{what} must be a non-empty string, got {value!r}")
    v = value.strip()
    if "/" in v:
        raise PathError(f"{what} must not contain '/': {value!r}")
    if v in (".", ".."):
        raise PathError(f"{what} must not be a relative path segment: {value!r}")
    return v


def customer_prefix(asiakas: str) -> str:
    """Everything belonging to one customer — the P-O-05 grant scope."""
    return f"{_seg(asiakas, 'asiakas')}/"


def case_prefix(asiakas: str, case: str) -> str:
    """Everything in one case — the P-O-06/07 single-case grant scope."""
    return f"{_seg(asiakas, 'asiakas')}/{_seg(case, 'case')}/"


def report_path(asiakas: str, case: str, report_id: str) -> str:
    return f"{case_prefix(asiakas, case)}report/{_seg(report_id, 'report_id')}"


def reports_prefix(asiakas: str, case: str) -> str:
    return f"{case_prefix(asiakas, case)}report/"


def material_path(asiakas: str, case: str, material_id: str) -> str:
    return f"{case_prefix(asiakas, case)}material/{_seg(material_id, 'material_id')}"


def material_config_path(asiakas: str, case: str, material_id: str) -> str:
    """Curation JSON for a material — grouping overrides, word merges, label edits.

    A sibling object rather than part of the material: the material is raw .sav
    bytes and cannot carry JSON, and the config is rewritten far more often than
    the .sav it describes.
    """
    return f"{material_path(asiakas, case, material_id)}.config"


def materials_prefix(asiakas: str, case: str) -> str:
    return f"{case_prefix(asiakas, case)}material/"


def template_path(asiakas: str, template_id: str) -> str:
    """Templates hang off the CUSTOMER, not a case — the Presentaatiopohjat card
    binds a template per asiakas/case/report with the lowest level winning, so a
    template must outlive any single case."""
    return f"{customer_prefix(asiakas)}template/{_seg(template_id, 'template_id')}"


def templates_prefix(asiakas: str) -> str:
    return f"{customer_prefix(asiakas)}template/"


def settings_path(key: str) -> str:
    return f"{SETTINGS_ROOT}/{_seg(key, 'key')}"
