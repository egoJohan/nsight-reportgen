# What nSight needs from datahive — API contract

_Date: 2026-08-17 · Status: draft for review · Card:
[Datahive ainoaksi tallennuskerrokseksi](https://trello.com/c/nUI0ZnYY)_

Companion: `2026-08-12-production-spec-requirements.md` (the Speksi 2 requirements this
serves).

## 1. The constraint that shapes everything

**No nSight-specific code may go into datahive.** That is datahive's floor rule 6 —
*"apps/integrations are DETACHED from core, BIDIRECTIONALLY … Before adding anything to
core, answer 'which extension does this belong to?'"*

So nSight gets no endpoints of its own. Every nSight concept — Asiakas, Case, Report,
Template, user, grant — must map onto a **generic** datahive primitive, and nSight's
domain model lives as *data inside those primitives*, never as datahive schema.

This is a stronger constraint than it first appears, and it turns out to be a
simplification: once the hierarchy is data, most of what looked like missing datahive
features stops being needed at all.

## 2. Integration shape

nSight talks to datahive over **HTTP REST only** — an `httpx` client against
`{base_url}/api/v1/…` with `Authorization: Bearer <macaroon>`, configured by
`NSIGHT_DATAHIVE_URL` / `_TOKEN` / `_TENANT`. It does not import datahive, share its
process, or touch its Postgres.

The entire coupling lives in one file: `src/reportbuilder/store/datahive_client.py`.
Nothing else in nSight knows datahive exists.

## 3. The four primitives nSight requires

| # | Primitive | Surface | State |
|---|---|---|---|
| P1 | Verbatim keyed documents | `/api/v1/projects/{ns}/docs` | ✅ complete |
| P2 | Keyed binary blobs | `/api/v1/projects/{ns}/blobs` | ⚠️ no DELETE |
| P3 | Groups and membership | `/api/v1/groups` | ✅ complete |
| P4 | Interactive human login | `/api/v1/ui/*` | ✅ complete |

**P1 — documents.** `POST /{ns}/docs` is documented as *"Attach a verbatim,
reference_id-addressable raw-doc"*: opaque text under a caller-chosen key, with a
`label` type tag. `GET /{ns}/docs?label=…` lists with **server-side** label filtering;
`GET`/`DELETE /{ns}/docs/{reference_id}` read and remove. "Verbatim" is the property
§8.2 depends on.

**P2 — blobs.** `POST /{ns}/blobs` (multipart, caller-chosen `reference_id`) and
`GET /blobs/{reference_id}` → raw bytes. No delete, and no listing.

**P3 — groups.** Create/list groups, add/remove/list members (members are identity
strings), lookup by name. All routes `require_admin`. Group *names are data* —
`hive_service.py:1419`: *"the group names are DATA, never code"* — so nSight-meaningful
group names introduce nothing nSight-specific into datahive.

**P4 — login.** See §5.

## 4. Mapping nSight's model onto the primitives

| nSight concept | Representation | Needs datahive work? |
|---|---|---|
| Customer (Asiakas) | doc, `label="customer"` | No |
| Case | doc, `label="case"`, carrying its customer ref | No |
| Report | doc, `label="report"` — already stored this way | No |
| Material | blob (the `.sav` bytes) + doc `label="material"` carrying name, blob ref **and its config** | No |
| Template | blob (the `.pptx`) + doc `label="template"` | Delete only |
| User | membership of an nSight-named group | No |
| Access grant | that same membership — see §6 | No |

Because Case is a document, `rename_case` and `delete_case` become an ordinary re-POST
and delete. Because material config rides *inside* the material doc, the missing
`/blobs/{id}/config` endpoint is not needed. Because materials are listed by
`?label=material`, the missing blob listing is not needed either.

**Every gap identified on 2026-08-17 except one disappears under this mapping.**

## 5. Authentication — nSight builds none

Datahive already has a complete interactive login system, and nSight's login page
consumes it rather than implementing one:

| Step | Endpoint | Purpose |
|---|---|---|
| 1 | `GET /api/v1/ui/config` | **Public, pre-auth.** Returns `login_oidc_issuer`, `hive_name`, `hive_slug`, `env`, and `providers` as `{id,label}` — exactly what a login screen needs, and no secrets |
| 2 | `GET /api/v1/ui/oidc/login` | Redirects to the hive's configured IdP; the callback mints a browser session |
| 3 | — | Session = short-TTL (600 s) access macaroon held in memory + **HttpOnly** refresh cookie + JS-readable CSRF cookie |
| 4 | `GET /api/v1/ui/session` | Whoami → `{identity, is_admin, tenant_id}`; `401` when anonymous |
| 5 | `POST /api/v1/ui/refresh` | Rotating refresh, triple-gated: `SameSite=Strict` + Origin/Referer match + double-submit CSRF |
| 6 | `POST /api/v1/ui/logout` | Clears cookies, revokes the refresh-token family |

**Consequence: no passwords exist anywhere in nSight.** Credentials live with the OIDC
provider. nSight never stores, hashes, resets or transmits a password — which removes an
entire class of security work and liability from this project.

**OIDC is not optional.** `POST /api/v1/ui/login` (the token-paste fallback) validates a
macaroon and then requires `is_admin_identity` — it is an **admin-only** path. So
ordinary nSight analysts have exactly one way in: the OIDC flow. If the nSight hive has
no `login_oidc_issuer` configured, `/oidc/login` returns 404 and **there is no
ordinary-user login at all**. See §11.2.

### 5.1 Provisioning is separate from authentication — and already built

The model: **an admin sets up which usernames may have access; the IdP proves who
someone is.** Datahive implements exactly this split, so nSight builds none of it.

| Step | Endpoint / mechanism | Who |
|---|---|---|
| Invite an email to a group | `POST /api/v1/hive_invite` — `{email, group="tenant_members", ttl_days=7 (1–90)}` | admin only |
| List invites | `GET /api/v1/hive_invite` — `{id, email, group, status, expires_at, created_at, accepted_at}` | admin only |
| Revoke | `POST /api/v1/hive_invite/{id}/revoke` | admin only |
| Authenticate | Google OIDC-RP — entirely separate, no invite knowledge | the IdP |
| Admit | `admit_via_invite` in the OIDC callback: the **verified** email is matched to a pending invite, which is consumed and the group membership added | datahive |

Properties worth relying on:

- **Un-invited means locked out.** A valid Google account with no matching invite gets a
  branded 403 — *"You need an invite to join"* — with no session minted and no redirect
  back to the client, audited as `oauth.oidc_rp.invite_denied`.
- **Invites cannot escalate.** `_PRIVILEGED_INVITE_GROUPS = ADMIN_GROUPS | {"hive-admin"}`
  is refused at create time, so nobody becomes an admin via an emailed link.
- **Revoke deprovisions.** Revoking an *accepted* invite also removes the granted group
  membership ("M6 teardown"), so revocation is the single offboarding action.
- **Invites expire** (1–90 days, default 7), so a forgotten invite does not linger as a
  permanent open door — or a permanent seat.
- **Optional domain auto-join.** `auto_join_domain` admits a whole verified email domain
  without individual invites, checked before the invite gate — useful if a customer wants
  everyone at their domain to have access.

**Consequence for the Käyttäjähallinta ticket:** "admin voi lisätä ja poistaa käyttäjiä ja
näiden oikeuksia" needs no user-management backend. It is an admin UI over
`hive_invite` + `groups`, plus nSight's own finer-grained customer/case authorization
(§6).

## 6. Authorization — membership is the single source of truth

Datahive's authority model, from `domain/admin_identity.py`:

> `ADMIN_GROUPS = {tenant_admins, owner}`. A caller is an admin iff their **OIDC-verified
> `subject_identity`** is a member of an admin group **in the store** — *"NEVER from the
> self-appendable `scope.groups` macaroon caveat, which a native holder can append at
> will to self-grant admin."* Fail-closed: no scope, no subject, no store, no tenant, or
> no membership all return `False`.

nSight adopts the same pattern rather than inventing one. That satisfies floor rule 2
(*"ALL rights resolved live in DataHive, never from a token or a frozen cache"*).

**The design rule that matters: membership *is* the access grant, not a mirror of it.**

nSight must not keep its own user list and *also* register members in datahive for
billing — the two would drift, and a user nSight forgot to register would have access
while generating no charge. Instead nSight resolves rights by asking datahive, so an
unprovisioned user simply has no access. Access control and the billing count become the
same fact and cannot diverge.

Requirements this must express (Käyttäjähallinta card + Speksi 2 P-O-05/06/07):

- A customer has an owner — its creator — with permanent read+write.
- Users and groups can hold read+write on a **customer**, inheriting to its cases and reports.
- A user may hold a grant on a **single case** without any grant on its customer (P-O-06/07).
- Effective right = own grant **OR** inherited from the parent customer **OR** ownership
  **OR** membership of a granted group.

## 7. Billing — seats are countable and audited

egoiq bills **50 €/user/month**, so the count must come from the platform, not be
self-reported by the billed application. Two calls:

```
GET /api/v1/groups/by-name/{group}   ->  {id, …}
GET /api/v1/groups/{id}/members      ->  ["identity", …]      # accepted seats
GET /api/v1/hive_invite              ->  [{email, status, expires_at, …}]
```

Group membership is the settled seat list: §5.1's admission adds a member on accept, and
revocation removes one, so the ledger maintains itself with no separate bookkeeping. The
invite list adds the not-yet-accepted cases — see §11.4 for whether those count.

Both are `require_admin`, so only egoiq can read them — nSight's customers can neither
inspect nor alter their own seat count.

**Better than a snapshot: it is audited.** `create_group`, `add_member` and
`remove_member` each `append_audit` with the actor, the action (`groups.add_member`), the
target group and `scope={"identity": …}`. So a billing period can be reconstructed and
*proved*, not merely observed — you can see when each seat appeared and disappeared.

**Later automation** (explicitly a later step) is a scheduled job over those two
endpoints, diffed against the audit log. Nothing further is needed from datahive.

**What counts as a billable user — SETTLED 2026-08-18 (johan): anyone who can log in to
nSight Studio.**

This is the simplest possible rule and it collapses the implementation: **one group whose
membership means "may log in to nSight Studio".** Its member count *is* the invoice line.

- No read-only vs read+write distinction to track — if you can log in, you are billable.
- No per-case or per-customer weighting — access *scope* is a separate, finer-grained
  concern inside nSight and has no billing effect.
- nSight's own administrators are billable, since they can log in.
- Counting is a single call, so the later automation is trivial.

Which makes the login gate and the seat ledger literally the same list, extending §6's
rule: membership is the access grant, and now also the invoice.

One wrinkle to decide before invoicing: **egoiq staff who log in for support would count
as seats under this rule.** Either accept that, or keep support access in a separate,
excluded group. See §11.4.

## 8. Cross-cutting requirements

Where a storage backend most easily betrays its caller.

### 8.1 Error semantics

nSight's `app.py` passes `400, 401, 403, 404, 409, 422` through to the UI and collapses
everything else to `502`. So datahive must distinguish:

- **401** — no/invalid token → the UI shows the login page
- **403** — authenticated but not permitted → "no access"
- **404** — absent, or not visible to this caller
- **409** — conflict, e.g. a uniqueness violation

Collapsing 403 into 404 is fine (it avoids leaking existence). Collapsing **401 into 403
is not** — the UI cannot then tell "log in" from "you may not".

### 8.2 Verbatim, byte-exact round-trip

Report JSON and material config must return **byte-identical**. This is not
fastidiousness: nSight's serde tests rest on `report_from_json(report_to_json(r)) == r`,
and the report model carries deliberate normalisation (a default `grouping` dict, an
unbackfilled `slide_id`) specifically to keep that equality true. A store that
reformats JSON, reorders keys or coerces numbers breaks report loading outright.

`.sav` and `.pptx` bytes likewise — nSight re-parses the `.sav` on every case open.

P1's documented "verbatim" contract is what makes this safe; it must stay true.

### 8.3 Deletes must state their cascade

Every delete needs one of two documented behaviours, never an implicit third: **refuse
with 409** while dependents exist, or **cascade atomically**.

Dependency edges: customer → cases → (materials, reports); material → reports built on
it; template → reports referencing it. The material case is sharpest — deleting a `.sav`
that reports depend on leaves reports that cannot render. The store audit already found
**4 orphan reports** belonging to no case, so this failure mode is not hypothetical.

### 8.4 Listings filtered server-side

Every list returns only what the caller may see. nSight must never receive a full list
and filter client-side — that leaks other customers' case names and makes the UI the
security boundary.

### 8.5 Capability discovery, not runtime 501s

nSight must be able to determine at startup what the connected hive supports, so an
unsupported operation fails loudly then rather than mid-session. The current
`getattr(client, "rename_case", None)` → 501 pattern in `routes_cases.py` is precisely
the anti-pattern to remove: it converts a missing backend capability into a runtime
surprise for the user.

### 8.6 Concurrency

Two analysts editing different reports in one case must not clobber each other. Report
save is a versioned replace keyed by `reference_id`; concurrent replaces of the *same*
report should be last-write-wins without corruption, or `409`. The store nSight runs on
today is single-process and cannot honour this — part of why this migration exists.

## 9. The only gap: DELETE on a blob

Under §4's mapping, one capability remains genuinely missing: removing a stored blob.
Required by P-C-01 (delete a dataset) and TE-4 (delete a template).

`references.py`'s `DELETE /{ref_id}` does not help — it removes knowledge-graph
reference triples (`ConceptReferenceRow`), not blobs.

This is a **generic** capability: anyone attaching blobs needs to detach them, and its
absence reads as an oversight rather than a missing feature. It introduces no
nSight-specific concept, so floor rule 6 does not bar it from core.

## 10. Explicitly not required

Aggregation — **verified 2026-08-17: `client.aggregate()` is called only from tests,
never from product code.** nSight parses the `.sav` in-process via `read_sav` and
computes every percentage, count, mean and cross-tab locally in `reportbuilder/stats/`.
Datahive is a store and an identity provider, not a compute engine. The client method is
a deletion candidate.

Also unused: rendering, PII/classification, enrichment, scheduling, connectors, gdrive.
Changes there cannot affect nSight.

## 11. Open decisions

### 11.1 Will the login endpoints be kept stable for nSight?

The six login endpoints in §5 were built to serve **datahive's own admin web UI** — they
sit under `/api/v1/ui/` and the code describes them as the *"Admin SPA backend"*.

The risk is ordinary: endpoints written for one known caller get changed whenever that
caller needs something different — a renamed field, a different cookie, a changed
response. That is normal and harmless while datahive's SPA is the only consumer. But
nSight would become a second consumer nobody is thinking about, and its **login** breaks
on a datahive release, with no warning and no workaround (per §5, OIDC through these
endpoints is the only ordinary-user path in).

So the decision is a commitment, not an analysis:

1. **Treat them as published API.** Free today; requires that datahive not change them
   without considering nSight. Worth pinning with a contract test in datahive so a
   breaking change fails CI rather than production.
2. **Give the session flow a stable home** — e.g. re-expose it under `/api/v1/auth/*`
   as explicitly public, leaving `/api/v1/ui/*` free to churn for the SPA's needs. A
   small, generic datahive change; no nSight-specific concept enters core.
3. **Don't depend on them** — not viable: there would be no ordinary-user login.

Recommendation: **1 plus the contract test.** It costs nothing now and converts a silent
production break into a failing build.

### 11.2 Is an OIDC issuer configured for the nSight hive?

Per §5 this is not optional: the token-paste fallback is admin-only, so without
`login_oidc_issuer` there is no ordinary-user login. Which IdP, and who administers it?

### 11.3 Do nSight administrators become datahive `tenant_admins`?

Every `/api/v1/groups` route is `require_admin`, and `ADMIN_GROUPS = {tenant_admins,
owner}`. So "nSight's administrators can add and remove users" means they hold real
datahive admin authority over that hive. Bounded by the hive being nSight-dedicated, but
it is more than user management strictly needs.

### 11.4 What is a billable user? — SETTLED

**Anyone who can log in to nSight Studio** (johan, 2026-08-18). Implemented as one group
gating login; its member count is the invoice. See §7.

Two remaining sub-decisions, both cheap now and awkward to retrofit once invoicing runs:

1. **egoiq's own staff.** Under the stated rule, support logins are seats. If that is not
   intended, support accounts need their own group, excluded from the count.
2. **Pending invites.** An invited person who has never logged in *can* log in, so the
   literal rule makes them billable from the moment of invitation rather than first
   login. Expired and revoked invites are plainly not billable. Recommend billing on
   **accepted group membership** — it is the unambiguous list, it self-maintains
   (§5.1), and it cannot charge for an invitation that was never taken up.

### 11.5 Speksi 2 deviation to confirm with nSight

Speksi 2 requires managing *"yksittäistä käyttäjätunnusta, **sen salasanaa** ja sen
käyttöoikeuksia"*. Under this design **nSight never handles passwords** — identity is the
IdP's, so "change my password" happens there. This is a better outcome (no credential
handling in nSight) but it is a literal deviation from the spec text.

**Status: not a decision for egoiq — it is a question for nSight.** Parked here so it is
raised at the next requirements discussion rather than discovered during acceptance. It
does not block implementation: the design is sound either way, and only the wording of
the requirement is at issue.

## 12. What this contract does not cover

The implementation order: which of these the current datahive rework satisfies, and in
what sequence nSight adopts them. Approach A — close each gap one capability at a time,
each verified against a live hive, then a single data cutover — is agreed and unaffected
by which specific gaps remain.
