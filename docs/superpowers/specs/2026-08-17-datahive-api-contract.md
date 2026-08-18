# What nSight needs from datahive — API contract

_Date: 2026-08-17, revised 2026-08-18 · Status: draft, **not yet verified against a live
hive** · Card: [Datahive ainoaksi tallennuskerrokseksi](https://trello.com/c/nUI0ZnYY)_

Companion documents:
- `2026-08-12-production-spec-requirements.md` — the Speksi 2 requirements this serves
- `../notes/2026-08-18-datahive-label-inconsistency.md` — a datahive change request this
  design deliberately does not block on

> **Verification status — VERIFIED LIVE 2026-08-18** against a purpose-built local hive
> (`nsight-dev`, port 7910, datahive `c88e1c84`, v0.2.4) and the local egohive
> (`43e84c8f`). Results in §13. Verifying mattered: it produced one finding that would
> have broken in production (§13.2, the consent gate on deletes) and one that removes a
> constraint the design had been working around (§13.3, labels now exist on objects).
>
> Baseline note: the first draft was read from source at `19742f55`. datahive has since
> moved ~30 commits; `groups.py`, `hive_invite.py`, `ui_api.py`, `workspaces.py` and
> `admin_identity.py` are **unchanged**, so the login, invite, groups and workspace-access
> findings carry over intact.

## 1. The constraint that shapes everything

**No nSight-specific code may go into datahive** — floor rule 6, *"apps/integrations are
DETACHED from core, BIDIRECTIONALLY."*

So nSight gets no endpoints of its own. Every nSight concept must map onto a generic
datahive primitive. This turned out to be a simplification rather than an obstacle: three
successive passes over this document each *removed* invention, and what remains is
smaller than what nSight has today.

## 2. Integration shape

HTTP REST only, `{base_url}/api/v1/…`, `Authorization: Bearer <macaroon>`. nSight does not
import datahive, share its process, or touch its Postgres. The entire coupling lives in
one file: `src/reportbuilder/store/datahive_client.py`.

**nSight calls datahive as the logged-in user, not as a service** (decision, johan
2026-08-18). Every store call carries the caller's macaroon, so datahive itself enforces
what that user may read and write. nSight's own authorization code stops being the only
thing keeping customers apart, and floor rule 2 — *"ALL rights resolved live in DataHive,
never from a token or a frozen cache"* — is honoured by construction.

The practical consequence: **the store seam takes an auth context on every call.** That is
cheap to design in now and expensive to retrofit, which is why it was settled first.

## 3. The primitives nSight requires

| # | Primitive | Surface | State |
|---|---|---|---|
| P1 | Path-addressed object store | `/api/v1/objects` | ✅ complete |
| P2 | Groups, membership, invites | `/api/v1/groups`, `/api/v1/hive_invite` | ✅ complete |
| P3 | Interactive human login | `/api/v1/ui/*` | ✅ complete, see §7.1 |
| P4 | Labels on stored things | `?label=` on every store | ✅ landed 2026-08-18 (`7ac9eaa3`), see §13.3 |

### P1 — the object store is the whole storage requirement

`datahive/api/routers/objects.py`, described in its own docstring as a *"Tenant- and
path-scoped OBJECT STORE (non-indexing file storage) … store a file and hand it back —
raw blob storage + retrieval, WITHOUT RAG indexing."*

```
PUT    /api/v1/objects              multipart: file, path, content_type
GET    /api/v1/objects?path=...     (or /{object_id})
GET    /api/v1/objects/list?path_prefix=...
DELETE /api/v1/objects?path=...
```

Why this store and not the alternatives:

- **not `items`** — items always chunk and embed (`_get_item_per_chunk`, Qdrant chunks,
  *"no general download surface"*). Report JSON must round-trip byte-exact, so a chunking
  knowledge store is disqualifying. Objects are explicitly `indexed=false`.
- **not `projects`/docs** — project docs are verbatim and would work, but a project
  carries workflow machinery nSight never uses (`/advance`, `/rules`,
  `template_ref="wftemplate:dataset-report-study"`), gives a flat space rather than a
  hierarchy, and has no delete for its blobs.

Properties this design relies on:

| Property | Mechanism |
|---|---|
| Verbatim | not chunked, embedded or classified — `indexed=false` |
| Text **and** binary in one primitive | report JSON, `.sav`, `.pptx` are all objects |
| Path-level ABAC | `scope.path_matches` over the caller's macaroon caveat |
| Workspace ("box") boundary | `_box_admits_read` / `box_write_allowed` |
| Prefix listing, ABAC-filtered | `/objects/list?path_prefix=`, *"never leak existence of an out-of-scope path"* |
| Change detection | `etag` on every object |
| Provenance | `owner_subject` from the caller's **verified** `subject_identity` |
| Encrypted at rest | AES-GCM under the tenant DEK |
| Audited | every write, read and delete |
| Blessed cross-app surface | its stated consumer is egoHive's `datahive_object_store` StorageBackend, server-to-server over this same API |

Stored metadata is exactly: `record_id, path, size, content_type, etag, workspace_uuid`,
plus `owner_subject`. **No labels** — see §8.

## 4. Mapping nSight's model — paths

Everything is an object at a path. Path carries **hierarchy**; labels carry **type**.

```
{asiakas}/{case}/report/{report_id}              label nsight:report
{asiakas}/{case}/material/{material_id}          label nsight:material   (.sav bytes)
{asiakas}/{case}/material/{material_id}.config   label nsight:config     (curation JSON)
{asiakas}/template/{template_id}                 label nsight:template   (.pptx)
settings/...                                     label nsight:settings
```

| nSight concept | Representation |
|---|---|
| Customer (Asiakas) | the first path segment |
| Case | the second path segment |
| Report / Material / Template / Settings | objects, typed by label |

Listing is `?path_prefix=` for hierarchy and `?label=` for type, combinable — so "this
case's reports" is `path_prefix={asiakas}/{case}/report/`, and "every template this
customer has" is `path_prefix={asiakas}/&label=nsight:template`.

**No workspace concept is involved.** An earlier draft mapped Asiakas onto a datahive
workspace; that was wrong — it reached for a single-active-workspace mechanism that no
longer exists (`_resolve_box`'s docstring still refers to "the legacy single workspace").
Paths do the job, and paths are what the verification in §13 actually exercised.

## 5. The store seam

The refactor target. Domain logic (customer/case/report/template) moves *up* into a
repository layer; only the bottom layer changes at cutover.

```
routes  ->  repository (nSight domain)  ->  store seam (4 methods)  ->  backend
```

```python
put_object(auth, path, data, content_type, labels=None) -> id
get_object(auth, path) -> bytes
list_objects(auth, path_prefix) -> [{path, size, content_type, etag}]
delete_object(auth, path) -> None
```

`labels` is an **optional passthrough**: ignored today, filtering when §8 lands, with no
call-site changes.

This replaces 12 entity-specific methods (`create_case`, `save_report`,
`attach_material`, `load_material_config`, …) across ~20 call sites in 7 files. It also
removes the `report_migration.py:104` → `client._save()` leak, which reaches into a
private method of the JSON store, by construction.

## 6. Path grammar — SETTLED

The grammar is §4. Two properties make it work, both verified live (§13):

- **Prefix listing** scopes to a subtree, so hierarchy queries are server-side.
- **Labels** give the type axis, so a path never has to encode *what* a thing is. This
  matters because renaming a path physically moves the object — with labels carrying
  type, a mis-shaped path is recoverable by relabelling rather than by moving data.

Access control is the same axis: a token's path caveat *is* the grant (§7.3).

## 7. Identity

### 7.1 Login — nSight builds none

| Step | Endpoint |
|---|---|
| Pre-auth discovery (public) | `GET /api/v1/ui/config` → `login_oidc_issuer`, `hive_name`, `providers` |
| SSO | `GET /api/v1/ui/oidc/login` |
| Session | short-TTL (600 s) access macaroon in memory + HttpOnly refresh cookie + CSRF cookie |
| Whoami | `GET /api/v1/ui/session` → `{identity, is_admin, tenant_id}`; 401 anonymous |
| Refresh | `POST /api/v1/ui/refresh` — rotating, `SameSite=Strict` + Origin/Referer + double-submit CSRF |
| Logout | `POST /api/v1/ui/logout` — revokes the refresh family |

**No password exists anywhere in nSight.** Credentials belong to the IdP.

**OIDC is not optional:** `POST /api/v1/ui/login` (token-paste) requires
`is_admin_identity`, so it is admin-only. Without `login_oidc_issuer` configured there is
no ordinary-user login at all. See §9.2.

### 7.2 Provisioning — admin sets who may enter, already built

`/api/v1/hive_invite`, admin-only: `POST ""` (`{email, group, ttl_days 1–90}`),
`GET ""`, `POST /{id}/revoke`. The OIDC callback runs `admit_via_invite`, matching the
**verified** email to a pending invite, consuming it and adding group membership.

- Un-invited → branded 403, no session minted, audited `oauth.oidc_rp.invite_denied`.
- Invites cannot confer a privileged group (`ADMIN_GROUPS | {"hive-admin"}` refused at
  create) — no self-escalation via an emailed link.
- Revoking an *accepted* invite also removes the group membership, so revocation is the
  single offboarding action.
- Optional `auto_join_domain` admits a whole verified email domain.

So *"admin voi lisätä ja poistaa käyttäjiä"* needs no backend — only an admin UI over
`hive_invite` + `groups`.

### 7.3 Authorization

Datahive's own model, from `domain/admin_identity.py`: authority is the **OIDC-verified
`subject_identity` ∩ the group-membership store**, *"NEVER from the self-appendable
`scope.groups` macaroon caveat"*. Fail-closed. nSight adopts the same pattern.

Speksi 2's two levels are both path caveats on the user's token — verified enforcing in
§13.1 (out-of-caveat read → 404, listings filtered to admitted paths only):

| Requirement | Token caveat |
|---|---|
| P-O-05 — access to a customer | `{asiakas}/**` |
| P-O-06/07 — access to a single case, without the customer | `{asiakas}/{case}/**` |

**Membership is the access grant, not a mirror of it.** nSight must not keep its own user
list alongside datahive's — they would drift, and a user nSight forgot to register would
have access while generating no charge.

**The one piece with real design work left:** turning a logged-in session into a macaroon
whose path caveats match that user's customers and cases.

### 7.4 Billing

**A billable user is anyone who can log in to nSight Studio** (johan, 2026-08-18) — one
group whose membership means "may log in"; its member count is the invoice, at 50 €/user/
month.

```
GET /api/v1/groups/by-name/{group}  ->  GET /api/v1/groups/{id}/members  ->  count
```

Both `require_admin`, so only egoiq can read them. Every membership change calls
`append_audit` with actor, action and `scope={"identity": …}`, so a period can be
*proved*, not merely observed. Later automation is a scheduled job over those two calls.

Sub-decisions still open: whether egoiq's own support logins count as seats, and whether
a pending invite counts before first login (recommend billing on accepted membership).

## 8. Labels — RESOLVED

datahive commit `7ac9eaa3` *"feat(labels): one label model for every store, instead of
three"* landed on 2026-08-18, adding `datahive/domain/labels.py` as the single
implementation, with an architecture test that fails if a store hand-rolls its own.

For nSight this means **path and type are separate axes**:

```
path:    <workspace>/case/<case_id>/...     where it belongs
labels:  nsight:report | nsight:material     what it is
```

Labels are hierarchical — writing `nsight:report` stores `["nsight", "nsight:report"]`
(verified §13.3) — so `?label=nsight` returns everything nSight owns.

`pinned_labels` were deliberately *not* generalised: they claim "the OWNER affixed this"
and are consumed by ABAC as `pinned_labels_required`, so they are an authorization input
rather than an organising axis. nSight does not need them.

Historical note: `../notes/2026-08-18-datahive-label-inconsistency.md` describes the
problem this fixed.

## 9. Open decisions

**9.1 Will `/api/v1/ui/*` be kept stable for nSight?** Those six login endpoints were
built to serve datahive's own admin SPA. If they change for the SPA's convenience,
nSight's *login* breaks with no workaround. Options: publish them as API (recommended,
plus a contract test so a break fails CI), re-expose the flow at a stable public path, or
don't depend on them (not viable — no login). Note the object store does **not** have this
problem: it is already a server-to-server surface for another product.

**9.2 Which IdP? — ANSWERED: egoHive.** The local egohive serves
`/.well-known/openid-configuration` with `issuer=http://localhost:8000`,
`authorization_endpoint=/api/v1/auth/oidc/authorize`, `token_endpoint=/api/v1/auth/oidc/token`,
`jwks_uri=/api/v1/auth/oidc/jwks.json`, EdDSA-signed. datahive's own `init` names it:
`--oidc-issuer  Trusted OIDC issuer (e.g. egohive) to accept JWT bearers from`. egohive
also exposes `/datahive/jwks.json` — *"the service-signing JWKS a DataHive instance
fetches to verify egoHive's data-path service tokens"*.

Remaining sub-task: the `nsight-dev` hive was initialised **without** OIDC
(`login_oidc_issuer: null`), so it must be re-initialised or reconfigured with
`--oidc-issuer` / `--oidc-jwks-url` pointing at egohive before login work starts.

**9.3 Do nSight administrators become datahive `tenant_admins`?** Every `/groups` and
`/hive_invite` route is `require_admin`, so "nSight admins add and remove users" means
real datahive admin authority over that hive.

**9.4 Path grammar** — §6.

**9.5 Speksi 2 wording.** The spec requires managing *"sen salasanaa"*; nSight never
handles passwords. A question for nSight, not egoiq; does not block implementation.

## 10. Explicitly not required

**Aggregation** — verified 2026-08-17: `client.aggregate()` is called only from tests.
nSight parses the `.sav` in-process via `read_sav` and computes every statistic locally in
`reportbuilder/stats/`. Datahive is a store and an identity provider, not a compute
engine; the client method is a deletion candidate.

Also unused: `items`/RAG, `projects`, rendering, PII/classification, enrichment,
scheduling, connectors, gdrive.

## 11. Cross-cutting requirements

Where a storage backend most easily betrays its caller. These survive unchanged from the
first draft and are what §12's verification must actually test.

**11.1 Error semantics.** nSight's `app.py` passes `400/401/403/404/409/422` through and
collapses the rest to `502`. Collapsing 403 into 404 is fine (hides existence);
collapsing **401 into 403 is not** — the UI cannot then tell "log in" from "you may not".

**11.2 Byte-exact round-trip.** Report JSON must return byte-identical: the serde tests
rest on `report_from_json(report_to_json(r)) == r`, and the model carries deliberate
normalisation to keep that true. `.sav` and `.pptx` likewise — nSight re-parses the `.sav`
on every case open.

**11.3 Deletes state their cascade.** Refuse with `409` while dependents exist, or cascade
atomically — never an implicit third thing. Edges: customer → cases → (materials,
reports); material → reports built on it; template → reports referencing it. The audit
already found **4 orphan reports**, so this is not hypothetical.

**11.4 Listings filtered server-side.** nSight must never receive a full list and filter
client-side — that leaks other customers' names and makes the UI the security boundary.

**11.5 Capability discovery, not runtime 501s.** The current
`getattr(client, "rename_case", None)` → 501 pattern converts a missing backend capability
into a mid-session surprise. Fail loudly at startup instead.

**11.6 Concurrency.** Two analysts editing different reports in one case must not clobber
each other; `etag` is the natural basis. Today's single-process JSON store cannot honour
this, which is part of why the migration exists.

## 12. Next step: verify against a live hive

Before any of this is built on, bring up a local datahive and exercise P1:

1. `PUT` then `GET` an object — is it **byte-identical**? (11.2)
2. `list?path_prefix=` — does it behave as read, and what exactly comes back?
3. Does `scope.path_matches` actually refuse an out-of-scope path? (7.3)
4. `DELETE ?path=` — and what happens to a prefix with children? (11.3)
5. What does minting a per-user macaroon with path caveats look like in practice? (7.3)

Approach A — close each gap one capability at a time, each verified live, then a single
data cutover — is agreed and unchanged.

## 13. Live verification results (2026-08-18)

Run against `nsight-dev` (port 7910, datahive `c88e1c84`), with three CLI-minted bearers:
unrestricted, path-caveated to `nsight-probe/allowed`, and read-only. All probe objects
were removed afterwards.

### 13.1 Confirmed

| Claim | Result |
|---|---|
| **Byte-exact round-trip (§11.2)** | ✅ A payload of NULs, `0xFF`, CRLF and the full 0–255 byte range returned **byte-identical**, as did UTF-8 JSON. This is the claim the report serde tests rest on. |
| **Path-scope enforcement (§7.3)** | ✅ The path-caveated token got **404** on an out-of-caveat path, **200** writing inside its caveat, and its listing showed 1 of 3 objects — datahive genuinely forces per-path permissions. |
| **Read-only tokens** | ✅ `PUT` with a `--read-only` bearer → **403**. |
| **Prefix listing (§11.4)** | ✅ Returns `object_id, path, size, content_type, etag, workspace_uuid, labels` — richer than the source implied, and ABAC-filtered. |
| **`/api/v1/ui/config` is public (§7.1)** | ✅ 200 with no token. |

### 13.2 NEW — destructive operations require consent elevation

`DELETE /api/v1/objects` returns **403** even for an unrestricted bearer:

```json
{"error": "consent_required",
 "consent": {"request_id": "cr_…", "reason": "object.delete is a destructive operation",
             "action": "object.delete", "target_kind": "path",
             "target_pattern": "nsight-probe/**",
             "desired_lifetime": {"kind": "one_shot"},
             "approval_urls": {"rest": "/api/v1/consent/requests/{id}/approve",
                               "cli": "datahive consent approve {id}",
                               "web": "/ui/consent/{id}"}}}
```

This is floor rule 4 — *"irreversible/destructive ops need explicit human approval"* — and
it applies to **every nSight delete**: dataset (P-C-01), template (TE-4), report, case.

**Design consequence.** nSight cannot treat delete as a plain call. Its UI must catch
`consent_required` and drive an approval — which is arguably the correct UX for
destroying an analyst's work anyway, but it is a flow that must be *designed*, not
discovered. The approve-then-retry cycle was verified working via the CLI route.
Whether nSight can hold a standing elevation instead of a one-shot per delete is an open
question.

### 13.3 NEW — labels landed, and work

Verified on the live hive: `PUT` with `labels=nsight:report` stored
`["nsight", "nsight:report"]` — hierarchical expansion applied — and
`GET /objects/list?label=nsight:report` filtered **server-side**, returning exactly the
matching object. See §8.

### 13.4 Environment

- **datahive `nsight-dev`** — port 7910, tenant `048a48ee-540a-467c-8c55-b925ec5447dd`,
  config `~/.local/share/datahive/nsight-dev/`, against the shared postgres :5433 and
  qdrant :6336. Health reports `postgres: true, qdrant: true, can_recall: true`.
  Note `datahive init` needs `--kms-profile dev` (default `prod` forbids FileKMS) and a
  `--qdrant-api-key`.
- **egohive** — already running on :8000, healthy; the stored `work/egohive_creds.json`
  still authenticates.
- Bearers for the dev hive are in `work/datahive_creds.json` (gitignored, mode 600).

### 13.5 Still unverified

The seam's remaining unknown: minting a **per-user** macaroon whose path caveats match
that user's customers and cases, from an egohive OIDC session rather than the CLI. The
CLI path (`datahive auth grant --paths`) is proven; the session-to-caveat path is not.
