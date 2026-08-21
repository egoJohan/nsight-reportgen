"""The path grammar: where an nSight object lives in datahive.

Path carries HIERARCHY, labels carry TYPE (design
`docs/superpowers/specs/2026-08-17-datahive-api-contract.md` §4/§6):

    {asiakas}/customer.json                          nsight:customer
    {asiakas}/{case}/case.json                       nsight:case
    {asiakas}/{case}/report/{report_id}              nsight:report
    {asiakas}/{case}/report/{report_id}.meta         nsight:report-meta
    {asiakas}/{case}/report/{report_id}.pptx         nsight:render
    {asiakas}/{case}/material/{material_id}          nsight:material
    {asiakas}/{case}/material/{material_id}.config   nsight:config
    {asiakas}/template/{template_id}                 nsight:template
    {asiakas}/template/{template_id}.meta            nsight:template-meta
    settings/{key}                                   nsight:settings
    settings/template/default.pptx                   nsight:template
    settings/font/{id}                               nsight:font
    settings/font/{id}.meta                          nsight:font-meta
    settings/user/{user_id}                          nsight:user
    settings/user/{user_id}.grants                   nsight:grants
    settings/user/{user_id}.password                 nsight:password
    settings/session/{session_id}                    nsight:session
    settings/invite/{invite_id}                      nsight:invite

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
LABEL_CUSTOMER = "nsight:customer"
LABEL_CASE = "nsight:case"
LABEL_REPORT = "nsight:report"
LABEL_REPORT_META = "nsight:report-meta"
LABEL_RENDER = "nsight:render"
LABEL_MATERIAL = "nsight:material"
LABEL_CONFIG = "nsight:config"
LABEL_TEMPLATE = "nsight:template"
LABEL_TEMPLATE_META = "nsight:template-meta"
LABEL_SETTINGS = "nsight:settings"
LABEL_FONT = "nsight:font"
LABEL_FONT_META = "nsight:font-meta"
LABEL_USER = "nsight:user"
LABEL_GRANTS = "nsight:grants"
LABEL_SESSION = "nsight:session"
LABEL_PASSWORD = "nsight:password"
LABEL_INVITE = "nsight:invite"

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


def customer_meta_path(asiakas: str) -> str:
    """Where a customer's name lives.

    The path segment is an id, not a name — a name in the path would make
    renaming a customer a data migration. So each container entity keeps a small
    JSON sidecar, and "list every customer" is `?label=nsight:customer` with no
    prefix: server-side, filtered by the caller's grants (not by datahive), and
    no directory concept needed.
    """
    return f"{customer_prefix(asiakas)}customer.json"


def case_meta_path(asiakas: str, case: str) -> str:
    """Where a case's name lives. Same reasoning as customer_meta_path."""
    return f"{case_prefix(asiakas, case)}case.json"


def customer_prefix(asiakas: str) -> str:
    """Everything belonging to one customer — the P-O-05 grant scope."""
    return f"{_seg(asiakas, 'asiakas')}/"


def case_prefix(asiakas: str, case: str) -> str:
    """Everything in one case — the P-O-06/07 single-case grant scope."""
    return f"{_seg(asiakas, 'asiakas')}/{_seg(case, 'case')}/"


def report_path(asiakas: str, case: str, report_id: str) -> str:
    return f"{case_prefix(asiakas, case)}report/{_seg(report_id, 'report_id')}"


def report_meta_path(asiakas: str, case: str, report_id: str) -> str:
    """Name and modification time for a report.

    A sidecar rather than fields inside the report JSON, because that JSON must
    round-trip byte-exact — injecting a timestamp would break
    report_from_json(report_to_json(r)) == r.

    It exists at all because datahive records no modification time: the object
    listing returns path/size/content_type/etag/labels and the GET carries no
    Last-Modified. Verified 2026-08-18.
    """
    return f"{report_path(asiakas, case, report_id)}.meta"


def report_render_path(asiakas: str, case: str, report_id: str) -> str:
    """The rendered deck for a report.

    Stored rather than left in a temp dir because a render is expensive
    (LibreOffice per PDF) and the temp dir dies with the process — staging loses
    every deck on deploy. It is still a CACHE: derived from the report, the
    material and the material's curation, so it is served only when a
    fingerprint of those still matches (see Repository.render_key).
    """
    return f"{report_path(asiakas, case, report_id)}.pptx"


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


def template_meta_path(asiakas: str, template_id: str) -> str:
    """Name and validation summary for a template. A sibling, like a material's
    config, because the .pptx cannot carry them."""
    return f"{template_path(asiakas, template_id)}.meta"


def templates_prefix(asiakas: str) -> str:
    return f"{customer_prefix(asiakas)}template/"


def default_template_path() -> str:
    """The house-style template every level falls back to.

    Under settings/ rather than a customer, because it belongs to nSight and is
    shared by every asiakas — a customer-scoped copy would drift per customer
    and defeat the point of a default.
    """
    return f"{SETTINGS_ROOT}/template/default.pptx"


def fonts_prefix() -> str:
    return f"{SETTINGS_ROOT}/font/"


def font_path(font_id: str) -> str:
    """A manually installed font file.

    Under settings/ because a font serves every customer: the render host needs
    Century Gothic once, not once per asiakas.
    """
    return f"{SETTINGS_ROOT}/font/{_seg(font_id, 'font_id')}"


def font_meta_path(font_id: str) -> str:
    return f"{font_path(font_id)}.meta"


def settings_path(key: str) -> str:
    return f"{SETTINGS_ROOT}/{_seg(key, 'key')}"


def user_path(user_id: str) -> str:
    return f"{SETTINGS_ROOT}/user/{_seg(user_id, 'user_id')}"


def user_grants_path(user_id: str) -> str:
    """Grants are a sibling of the user, not part of it: they are rewritten far
    more often than the identity they belong to, exactly as material curation is
    a sibling of the .sav."""
    return f"{user_path(user_id)}.grants"


def user_password_path(user_id: str) -> str:
    """A sibling of the user, like grants — rewritten independently of the
    identity it belongs to."""
    return f"{user_path(user_id)}.password"


def session_path(session_id: str) -> str:
    return f"{SETTINGS_ROOT}/session/{_seg(session_id, 'session_id')}"


def invite_path(invite_id: str) -> str:
    """Keyed by the invite's own id, not the invited email.

    The id doubles as the invitation's token: `get_invite`/`delete_invite`
    take only this id, so whoever holds it can look the record up (and,
    once accepted, could be handed the account it names) without ever
    knowing the email it was sent to -- the id must therefore be generated
    unguessably (`Repository.create_invite` uses `secrets`, not `_new_id`'s
    uuid4). Keying by email instead would put a second copy of the
    invited person's address in the path segment for no benefit, since
    admin lookup by email is already served by scanning
    `list_invites`/`find_pending_invite_by_email` the same way
    `find_user_by_email` scans `list_users`.
    """
    return f"{SETTINGS_ROOT}/invite/{_seg(invite_id, 'invite_id')}"
