# What nSight needs from datahive — API contract

_Date: 2026-08-17 · Status: draft for review · Card:
[Datahive ainoaksi tallennuskerrokseksi](https://trello.com/c/nUI0ZnYY)_

This document specifies the capabilities nSight requires from datahive, **stated from
nSight's side**. It deliberately describes *what must be true*, not how datahive
implements it — datahive is being reworked, so a contract expressed as required
behaviour survives that refactor while an inventory of today's routes does not.

Companion: `2026-08-12-production-spec-requirements.md` (the Speksi 2 requirements this
serves).

---

## 1. Integration shape

nSight talks to datahive over **HTTP REST only**: an `httpx` client against
`{base_url}/api/v1/…` with `Authorization: Bearer <token>`, configured by
`NSIGHT_DATAHIVE_URL` / `_TOKEN` / `_TENANT` (`reportbuilder/config.py`). It does not
import datahive, share its process, or touch its Postgres. The entire coupling is this
REST surface, in one file: `src/reportbuilder/store/datahive_client.py`.

That matters for the migration: the contract below is the complete integration surface.
Nothing else in nSight knows datahive exists.

## 2. What datahive is — and is not — for nSight

**It is** the durable store for five kinds of thing, plus the identity provider:

| Kind | Content | Who owns the schema |
|---|---|---|
| Customer (Asiakas) | name, ownership | nSight concept, new |
| Case | name, parent customer | nSight concept |
| Material | `.sav` binary | SPSS format, opaque to datahive |
| Material config | JSON sidecar — grouping overrides, word merges, label overrides | nSight, opaque to datahive |
| Report | report-definition JSON | nSight, opaque to datahive |
| Template | `.pptx` binary | PowerPoint format, opaque to datahive |

**It is not** a compute engine. nSight reads the `.sav` in-process via `read_sav` and
computes every percentage, count, mean and cross-tab locally in
`reportbuilder/stats/`. Verified 2026-08-17: `client.aggregate()` is called **only from
tests**, never from product code. Datahive's aggregation endpoint is therefore *not*
part of the required contract, and the client method is a candidate for deletion.

Also out of scope: rendering, PPT generation, PII classification, enrichment,
scheduling, connectors. nSight uses none of them.

## 3. Required capabilities

Status column is against datahive `master` at `19742f55` (2026-08-17) and **must be
re-verified** after the current rework. `—` means nSight has no client method yet either.

### 3.1 Customer (Asiakas) — new, required by P-O-01

Speksi 2 requires a three-level hierarchy Asiakas → Case → Raportti. nSight's Case maps
to a datahive project today; the level *above* has no mapping yet.

| ID | Capability | Required semantics | Status |
|---|---|---|---|
| CU-1 | Create customer | name → stable id | — |
| CU-2 | List customers | **filtered server-side** to what the caller may see | — |
| CU-3 | Get / rename customer | | — |
| CU-4 | Delete customer | cascade behaviour must be explicit — see §4.3 | — |
| CU-5 | Customer is a case's parent | every case resolves to exactly one customer | — |

**Open:** does Asiakas map to a datahive *workspace*, to a parent project, or to a new
concept? This is the one decision that most shapes the rest. See §5.1.

### 3.2 Case

| ID | Capability | Required semantics | Status |
|---|---|---|---|
| CA-1 | Create case under a customer | name + parent → stable id | partial — create exists, no parent |
| CA-2 | List cases of a customer | filtered server-side to caller's rights | partial — lists all projects |
| CA-3 | Get case | name, parent, created | ✅ |
| CA-4 | **Rename case** | | ❌ `routes_cases.py:51` → 501 |
| CA-5 | **Delete case** | cascade over materials, configs, reports — §4.3 | ❌ `routes_cases.py:67` → 501 |

### 3.3 Material (the `.sav` blob)

| ID | Capability | Required semantics | Status |
|---|---|---|---|
| MA-1 | Attach material under a case | multipart upload → stable id | ✅ |
| MA-2 | Fetch raw bytes | `application/octet-stream`, **byte-exact** — nSight re-parses these | ✅ |
| MA-3 | **List a case's materials** | id + name per material | ❌ absent — only POST exists |
| MA-4 | **Delete material** | required by P-C-01; dependent-report behaviour — §4.3 | ❌ |
| MA-5 | **Get / put material config** | opaque JSON sidecar keyed by material; absent ⇒ **404**, not `200 null` | ❌ |

**MA-5 is the highest-risk gap.** It holds grouping overrides, word merges and
category-label overrides — hand-authored curation, often hours of analyst work. Against
a real datahive today the read 404s and is silently swallowed as "no config", and the
write raises. nSight's own client documents it as unverified: *"Assumed datahive
contract … NOTE: verify against the live datahive … VERIFY."*

### 3.4 Report (the definition doc)

| ID | Capability | Required semantics | Status |
|---|---|---|---|
| RE-1 | Save report | create **or versioned-replace by `reference_id`**, idempotent | ✅ |
| RE-2 | Load report | returns the stored text **byte-exact** — see §4.2 | ✅ |
| RE-3 | List a case's reports | id + name; filterable by label | ✅ |
| RE-4 | Delete report | | ✅ |

Duplicate-report (P-C-06) needs nothing new: nSight does it as load + save under a new
`reference_id`.

### 3.5 Template (the `.pptx`) — new, required by P-O-11

| ID | Capability | Required semantics | Status |
|---|---|---|---|
| TE-1 | Upload template | binary + name → stable id | — |
| TE-2 | List templates | visible to caller | — |
| TE-3 | Fetch template bytes | byte-exact | — |
| TE-4 | Delete template | refuse or cascade if reports reference it — §4.3 | — |

**Scope constraint:** the [Presentaatiopohjat](https://trello.com/c/oyZyWDx9) card binds
templates at customer, case *and* report level, lowest level winning. So templates
cannot live only under a case — they need customer-level or hive-level storage, and a
report stores a reference to one.

### 3.6 Identity and authorization — new

Datahive floor rule 2: *"Token is just a key — identity+tenant+expiry only; ALL rights
resolved **live** in DataHive, never from a token or a frozen cache."* The contract
below is written to respect that: nSight asks datahive about rights per request and
caches nothing.

| ID | Capability | Required semantics | Status |
|---|---|---|---|
| ID-1 | Authenticate a person | credential → token. **Owner unresolved — §5.2** | ❌ no password auth in datahive |
| ID-2 | Whoami | token → actor identity + tenant | ✅ via auth middleware |
| ID-3 | Users: create, list, delete | admin-only per the Käyttäjähallinta card | — |
| ID-4 | Groups: create, list, add/remove member | | ✅ `postgres_store/groups.py` |
| ID-5 | Grants: grant/revoke/list read+write on a **customer or a case**, for a user or a group | case-level grant is mandatory — P-O-06/07 | partial — `grants.py` exists |
| ID-6 | Resolve effective rights live | "may actor A read/write object X", inheritance applied | partial |

Effective-rights rule nSight needs answered, from the Käyttäjähallinta card plus Speksi 2:

> A customer has an owner (its creator) with permanent read+write. Users and groups can
> be granted read+write on a customer, inheriting to its cases and reports. **A user may
> additionally hold a grant on a single case without any grant on its customer.**
> Effective right = own grant **OR** grant inherited from the parent customer **OR**
> ownership **OR** membership of a granted group.

### 3.7 Explicitly not required

Aggregation (§2), rendering, PII/classification, enrichment, scheduling, connectors,
gdrive. If datahive's rework changes these, nSight is unaffected.

## 4. Cross-cutting requirements

These apply to every capability above and are where a storage backend most easily
betrays its caller.

### 4.1 Error semantics

nSight's `app.py` passes `400, 401, 403, 404, 409, 422` through to the UI and collapses
anything else to `502`. So datahive must distinguish:

- **401** — no/invalid token (UI shows login)
- **403** — authenticated but not permitted (UI shows "no access")
- **404** — object absent *or* not visible to the caller
- **409** — conflict, e.g. a name uniqueness violation

Blurring 403 into 404 is acceptable (it avoids leaking existence). Blurring 401 into 403
is not — the UI cannot tell "log in" from "you can't".

### 4.2 Verbatim, byte-exact storage

Report JSON and material config must round-trip **byte-identical**. This is not
fastidiousness: nSight's serde tests rest on
`report_from_json(report_to_json(r)) == r`, and the report model carries deliberate
normalisation (a default `grouping` dict, an unbackfilled `slide_id`) precisely to keep
that equality true. A store that reformats JSON, reorders keys, or coerces numbers
breaks report loading.

Likewise `.sav` and `.pptx` bytes must return exactly as stored — nSight re-parses the
`.sav` on every case open.

### 4.3 Deletes must state their cascade

Every delete needs one of two documented behaviours, never an implicit third:

- **Refuse** with `409` while dependents exist, or
- **Cascade** and delete dependents atomically.

Dependency edges: customer → cases → (materials, reports); material → its config;
material → reports built on it; template → reports referencing it. The material case
(MA-4) is the sharp one — deleting a `.sav` that reports depend on would leave reports
that cannot render. The store audit already found **4 orphan reports** belonging to no
case, so this failure mode is not hypothetical.

### 4.4 Listings are filtered server-side

Every list operation must return only what the caller may see. nSight must never receive
a full list and filter it client-side — that leaks names of other customers' cases, and
it would make the UI's own filtering the security boundary.

### 4.5 Capability discovery

nSight must be able to determine what the connected datahive supports, so an
unsupported operation fails **loudly at startup** rather than as a mid-session 501. The
current `getattr(client, "rename_case", None)` → 501 pattern in `routes_cases.py` is the
anti-pattern to remove: it turns a missing backend capability into a runtime surprise for
the user.

### 4.6 Concurrency

Two analysts editing different reports in the same case must not clobber each other.
Report save is a versioned replace keyed by `reference_id`; concurrent replaces of the
*same* report should be last-write-wins with no corruption, or `409`. The store nSight
runs on today is single-process and cannot honour this, which is part of why this
migration exists.

## 5. Open decisions

Each of these changes the design, and none can be resolved from nSight's side.

### 5.1 Where does Asiakas map?

Candidates: a datahive **workspace** (the stable top-level container in datahive's own
path model, `workspace/app/specifier`); a **parent project**; or a new concept. This
choice determines whether grants hang off existing datahive machinery or need new
plumbing, so it should be settled first.

### 5.2 Who owns password authentication?

Datahive has none — no `bcrypt`, `argon2`, `passlib` or `password_hash` anywhere;
login is OAuth-based and callers arrive with bearer tokens. Speksi 2 requires managing
*"yksittäistä käyttäjätunnusta, **sen salasanaa** ja sen käyttöoikeuksia"*. Three ways:

1. **nSight owns login** — its own password hashing and session, datahive stores the
   accounts and grants. Matches the spec literally; makes nSight a credential holder.
2. **Reuse datahive OAuth** — no passwords in nSight. Cleanest against datahive's rules,
   but "change your password" moves to an external provider: a spec deviation to confirm
   with nSight.
3. **Add password auth to datahive core** — centralises identity for all egoHive
   products, but it is a substantial change to a security-critical component whose floor
   rule 1 is *"never compromise security"*, requested by no other product.

### 5.3 Whose ids?

Does nSight keep its own identifiers and store them as datahive `reference_id`s (today's
pattern — `material-<uuid>`, `report-<uuid>`), or adopt datahive-issued ids? Today's
pattern makes the migration much easier, because existing staging ids can be carried
across unchanged.

### 5.4 Template scope level

Per §3.5, customer-level at minimum. Confirm whether templates should also be shareable
hive-wide across customers.

## 6. What this contract does not yet cover

The **implementation** side: which of these datahive already satisfies after the current
rework, which need building, and in what order. That is deliberately deferred until
datahive settles (see the card comment on `nUI0ZnYY`). Approach A — close the parity gap
one capability at a time, each verified against a live hive, then a single data cutover —
is agreed and unaffected by which specific gaps remain.
