# User management and permissions

_nSight Studio · design · 2026-08-20_

## 1. What this is for

Today nSight has no login. Every request carries a dev bearer from
`NSIGHT_DATAHIVE_TOKEN`, and anyone who reaches the app sees everything. This
design adds people: who may sign in, who may see which customer, and who may
change what.

Three things the customer asked for, in their words:

* sign-in with **Google and O365** — no passwords anywhere;
* **invitations** — an admin adds someone and they receive an email with a link
  to sign in;
* **permissions** — access to a customer, or to a single study without its
  customer, and read-only as well as edit.

## 2. Constraints that shaped it

**All data lives in datahive.** Attaching a different datahive to an nSight
backend must bring everything with it: settings, users, permissions, customers,
studies, reports, templates, fonts. nSight keeps nothing of its own but caches
it can rebuild. This is a requirement, not a preference, and §8 lists the one
place the current code breaks it.

**Users are datahive's; authorisation is nSight's.** Every user is an ordinary
read-write member of the tenant. Which customers a user may see, and whether
they may edit, is decided by nSight code and *stored* in datahive as data.

**Administered from nSight Studio.** datahive is the store of record; the
screens are in nSight's Settings.

## 3. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Google + O365 only. No passwords. | Credentials stay with the IdP. Nothing to hash, reset, rotate or leak. |
| D2 | nSight is the OIDC relying party, not datahive. | Users must never hold a hive token — see D3. |
| D3 | Only the nSight backend holds a datahive token. | Every user's token would be tenant-wide read-write, so a browser-held token could bypass nSight and reach any customer. Since nSight's checks are now the only separation between customers, they must be unbypassable. |
| D4 | Permissions are nSight's, stored in datahive. | Path caveats express *which data*, not *what you may do*. Read-only per grant needs a second axis datahive does not have. |
| D5 | nSight owns invitations end to end. | datahive's `hive_invite` gates admission to *datahive*, which our users never perform, and its email links to the hive's own URL. |
| D6 | At least two admins, enforced. Plus domain auto-join. | An admin on holiday must not block colleagues. |

**D5 supersedes the datahive contract's §7.2**, which concluded invitations
"need no backend — only an admin UI over `hive_invite`". That was written
assuming users log into datahive directly. D3 changed the premise; the contract
document should be annotated rather than left to disagree silently.

## 3.1 The first admin

D6 covers an admin being unavailable; it does not say how the first one exists.
On a hive with no users, the first person to sign in successfully becomes an
admin **only if their verified email appears in `NSIGHT_BOOTSTRAP_ADMINS`** — an
environment variable on the nSight server listing one or more addresses.

Deliberately an environment variable rather than a datahive record: it is the
one decision that cannot come from the store, because the store is empty at that
moment. Deliberately not "first sign-in wins": a fresh deployment reachable on
the internet would otherwise hand admin to whoever found it first.

Once an admin exists the variable stops being consulted. Losing every admin
afterwards is recovered by setting it again and signing in — the break-glass
path, available to whoever operates the server.

## 4. Identity and session

1. The user picks *Sign in with Google* or *with Microsoft*. nSight redirects.
2. The provider returns a signed identity token. nSight verifies signature,
   issuer, audience and expiry, and takes the **verified email** — never one
   the browser supplies.
3. nSight resolves that email to a user: a known user; a pending invitation
   (consume it, create the user with its grants); or an allowed email domain
   (create with the default grants). Anything else is refused with no session
   and an audit line.
4. nSight mints **its own** session: an HttpOnly, `SameSite=Strict`, `Secure`
   cookie holding a signed, opaque session id. Rotating, revocable, and short
   enough that removing access takes effect promptly (§7).
5. Every request resolves the cookie to a user, loads their grants, and calls
   datahive with nSight's service credential.

`deps_store.get_auth` stops returning the caller's bearer and returns nSight's
service identity together with the resolved user. **The store seam is
unchanged** — it still takes an auth context per call; that context now means
"nSight, acting for Maija" rather than "Maija". Writes carry the acting user so
datahive's audit does not attribute everything to the service.

## 5. Permissions

A **grant** is a path prefix and a mode:

```
{scope: "attendo",            mode: "edit"}   the customer and everything under it
{scope: "attendo/case-9b32",  mode: "view"}   one study, without its customer
```

The two scopes are Speksi 2's P-O-05 and P-O-06/07, expressed as data rather
than as a token caveat. `mode` is `view` or `edit`.

**Admin is a flag on the user, not a grant.** It confers managing users,
invitations and permissions — not access to data. An admin who has not been
granted Attendo does not see Attendo. Administering access and having access are
different things, and conflating them is how admin accounts quietly become
god accounts.

**One enforcement function**, in one module:

```python
may_read(user, path) -> bool
may_write(user, path) -> bool
```

Listings filter through the same function, so an ungranted customer is
**absent, not forbidden** — consistent with datahive's own rule that a listing
never leaks the existence of an out-of-scope path.

Routes reach it by three different dependencies, because they are not addressed
uniformly:

| Shape | Count | Guard |
|---|---|---|
| `/customers/{cid}/…` and `/cases/{case_id}/…` | ~30 | The id is in the path. Resolve, check, done. |
| `/materials/{material_id}/…` | **17** | The path names no customer. Resolve material → case → customer first (§5.1). |
| `/reports/recent`, `/settings/…`, `/chart-types` | 6 | Not addressed by data at all (§5.2). |

### 5.1 The material-addressed routes

Seventeen routes — every AI endpoint, chat, `preview-chart`, `questions`,
`word-merges` — are keyed by a bare material id from before the hierarchy
existed. They are also the routes that serve the actual survey data, so leaving
them unguarded would expose every customer's answers to anyone with an id.

`Repository.find_material` already resolves one, but **it lists every
`nsight:config` object in the tenant to do it**, and these routes are called per
chart. Two consequences:

* Resolution must be **cached** per request and across requests
  (material id → case, customer), invalidated on material delete. Without this
  the AI batch does ~60 tenant-wide listings per report.
* Its docstring says the listing is "already permission-filtered". Under D3 that
  is **no longer true** — see §5.3.

### 5.2 Routes not addressed by data

* `/reports/recent` spans customers by design (it is the landing page). It must
  filter its results through `may_read`, not merely require a session.
* `/settings/font-substitutions`, `/settings/chart-font`, `/settings/fonts`
  change what **every** render looks like, for everyone. Admin only.
* `/chart-types` is static metadata. Session only.

### 5.3 The assumption D3 invalidates

Six places in the current code rely on datahive filtering a listing by the
caller's own token — `deps_store` ("nSight talks to datahive AS THE LOGGED-IN
USER"), `paths.py` ("permission-filtered"), and four methods in `repository.py`
including `list_customers` ("datahive decides what this user may see — never
this class") and `find_material`. A seventh is `list_recent_reports`, whose
docstring promises "the caller's most recently modified reports, across every
customer" while listing every `nsight:report-meta` object in the tenant — under
D3 that becomes *everyone's* reports on the landing page.

Under D3 every one of those listings is made with nSight's service credential
and returns **the whole tenant**. Nothing throws; the filtering simply stops
happening. This is the single most dangerous consequence of the design and it
must be handled explicitly:

1. Audit those six sites and make each one filter through `may_read`.
2. Correct the comments, which will otherwise keep asserting a guarantee that no
   longer holds.
3. Add the route census in §11 so a new listing cannot quietly inherit the same
   mistaken assumption.

Rules that are enforced rather than documented:

* The last admin cannot be removed or demoted. Refused, with the reason.
* Domain auto-join creates a user with the default grants from
  `settings/access.json`, which may be empty — a colleague gets in and sees
  nothing until granted something.
* A grant naming a customer or case that no longer exists is ignored, the way a
  template binding to a deleted file is (see `resolve_template`).

### 5.4 Where the session cookie actually works

A cookie only reaches the backend if the browser considers it same-origin, and
the two deployments differ:

* **Production**: `web/nginx.conf` proxies the API under the app's own origin,
  so an `HttpOnly; SameSite=Strict` cookie works as intended.
  **But it proxies an allowlist — `/cases`, `/materials`, `/chart-types` only.**
  `/customers`, `/settings` and `/reports/recent` are already absent, and
  `/auth/*` would be too. This must be a prefix that covers the API, or every
  new route is a production 404 that development never sees.
* **Development**: Vite serves the UI on `:5180` and `api.ts` calls
  `http://127.0.0.1:8200` directly — **cross-origin**, so a `SameSite=Strict`
  cookie is never sent. Worse, CORS is configured `allow_origins="*"` with
  `allow_credentials=False`, which forbids credentialed requests outright.

The fix is a Vite dev proxy so both environments are same-origin, rather than
relaxing `SameSite` and enabling credentialed CORS — which would weaken the
production posture to suit development. `VITE_API_BASE` becomes a relative path.

## 6. Invitations

An admin adds a person by email, with their initial grants. nSight records the
invitation, sends an email containing a link to **nSight's** login, and shows
the admin the same link to copy.

The person clicks it, signs in with Google or Microsoft, and nSight matches the
**verified** email to the pending invitation, applies its grants, and creates
the user.

**The link is not a credential.** Forwarding the email gains the recipient
nothing: they must still authenticate as that verified address, and the grants
attach to the address rather than to the link. This is what makes it safe to
send an invitation by email at all.

Delivery may fail without failing the invitation: the record is created either
way and the UI shows `emailed: false` with the link to copy, rather than
pretending it was sent.

Email is sent by nSight through a provider configured in
`settings/email.json` — SMTP or an API provider. Consistent with §2 the
configuration lives in datahive, so moving hive moves the mail setup too.
Invitations expire (default 14 days) and can be revoked; revoking an accepted
invitation removes the user.

## 7. Revocation and sessions

Removing a user's access must take effect without waiting for a token to
expire. Sessions are therefore resolved against stored state rather than being
self-validating: deleting a user, or their session, ends it.

Resolving from datahive on **every** request would put a network round trip in
front of every call, against a hive sized at 1 CPU. So the resolved session and
its grants are cached in the nSight process for a short TTL (30 s). The cost is
bounded: a revocation takes effect within that window, and a sign-out evicts
immediately on the node that handled it.

If nSight is ever run as more than one process, that TTL becomes the revocation
guarantee across the fleet — worth stating now, because it is the kind of
assumption that silently stops holding when a second instance appears.

Sessions carry an absolute lifetime and an idle timeout; sign-out deletes the
record.

## 8. What has to move

`web/src/lib/workspace.ts` keeps a per-case workspace in `localStorage` — the
material pointer and report timestamps. Under §2 that must move to
`settings/user/{id}.workspace` in datahive; otherwise attaching a different hive
leaves a user's state behind and the requirement is not met.

Two deployment changes fall out of §5.4:

* `web/nginx.conf` must proxy the API by prefix rather than by an allowlist of
  three paths.
* `web/vite.config.ts` gains a dev proxy, and `VITE_API_BASE` becomes relative.

## 8.1 Implementation surface

**Backend — new `reportbuilder/auth/`:**

| Module | Responsibility |
|---|---|
| `oidc.py` | Verify Google and Microsoft identity tokens: signature, issuer, audience, expiry. Returns a verified email or raises. |
| `session.py` | Mint, resolve, refresh and revoke sessions; the 30 s cache of §7. |
| `permissions.py` | `may_read` / `may_write`, and the grant model. The security-critical file. |
| `invites.py` | Create, consume, revoke; the email body and the link. |

**Backend — changed:**

* `api/deps_store.py` — `get_auth` returns nSight's service identity plus the
  resolved user (§4). New dependencies: `require_session`, `require_admin`,
  `require_access(path, write=…)`, `require_material_access` (§5.1).
* `store/repository.py` — users, grants, invitations, sessions; and the seven
  listing sites of §5.3 filtered through `may_read`.
* `api/routes_*.py` — each route declares its guard. Public: the login routes
  and `/health` only.
* `api/server.py` — CORS and cookie settings per §5.4.

**Frontend — new:** a `/login` page with the two provider buttons; a session
hook that redirects on 401; a Users section in Settings (list, invite, revoke,
edit grants, admin toggle), following the shape of the templates panel.

**Frontend — changed:** `lib/api.ts` sends credentials and uses a relative base;
`lib/workspace.ts` reads and writes through the API rather than `localStorage`
(§8); `vite.config.ts` gains the dev proxy.

**Order of work.** The permission model and its tests come first and can land
while the app still uses the dev bearer — `may_read` is testable without a login
existing. Sign-in follows. The §5.3 audit lands with the permission model, not
after it, because that is the window in which listings silently stop being
filtered.

## 9. Data model

Following the existing path grammar (`paths.py`: hierarchy in the path, type in
a label):

```
settings/user/{user_id}          nsight:user     email, name, is_admin, created, last_seen
settings/user/{user_id}.grants   nsight:grants   [{scope, mode}, …]
settings/user/{user_id}.workspace nsight:workspace  per-case UI state (§8)
settings/invite/{invite_id}      nsight:invite   email, grants, invited_by, expires, emailed
settings/session/{session_id}    nsight:session  user_id, created, last_seen, expires
settings/access.json             nsight:settings allowed domains, default grants
settings/email.json              nsight:settings provider and credentials
settings/oidc.json               nsight:settings Google and Microsoft client ids/secrets
```

Client secrets and the session-signing key live in datahive rather than in
environment variables, so §2 holds: attaching a hive brings the sign-in
configuration with it. datahive encrypts objects at rest under the tenant DEK.
The one exception is `NSIGHT_BOOTSTRAP_ADMINS` (§3.1), which cannot come from
the store it exists to populate.

## 10. Errors

| Situation | Result |
|---|---|
| No session | 401. The frontend redirects to the login page. |
| Session valid, no grant for the path | Reads: absent from listings; direct fetch 404. Writes: 403. |
| `view` grant, write attempted | 403, with the reason. |
| Verified email matches nothing | Sign-in refused, no session, audit line. |
| Email delivery fails | Invitation stands; UI offers the link. |
| OIDC provider unreachable | Sign-in fails with a plain message. Existing sessions are unaffected. |

## 11. Testing

Two kinds carry the weight:

* **A permission matrix** exercising `may_read` / `may_write` directly: a viewer
  cannot write; a customer grant reaches its cases; a case grant does **not**
  reach its customer; an ungranted customer is invisible rather than forbidden;
  an admin without a grant still sees nothing.
* **A fail-closed route census**: enumerate every route on the app and assert
  that each either requires a session or is explicitly listed as public. This is
  what keeps the guarantee true as routes are added, rather than relying on
  everyone remembering.

* **A listing-leak test** per §5.3: with two customers and a user granted one,
  assert that `list_customers`, `list_cases`, `/reports/recent` and
  `find_material` each return only the granted one. These are the calls that
  used to be filtered by datahive and no longer are.

Plus: the last-admin rule; invitation consumed exactly once; a revoked user's
next request failing; email failure leaving a usable invitation; and a
material-addressed route refusing an id belonging to another customer.

## 12. Risks

**nSight's code is the only thing separating customers.** D3 makes it
unbypassable from a browser, but a bug in `may_read` is now a data-leak between
customers rather than a UI slip. This is the cost of D4, accepted deliberately:
the permission matrix in §11 is the mitigation, and it should be treated as
security-critical rather than as ordinary coverage.

**The failure mode is silent.** §5.3 is the sharp edge: six existing listings
stop being filtered without erroring, and a route added later inherits the same
trap. Loud failure would be safer, but datahive cannot know what nSight intends;
the census test in §11 is the substitute.

**Material ids are not secrets.** They are random, but the seventeen routes in
§5.1 currently treat possession of an id as authorisation. Until §5.1 lands,
anyone with a session can read any material by id.

**The service credential is a standing key to the whole tenant.** It lives on
the nSight server. Compromising that server exposes every customer — which was
true before this design and is not made worse by it, but is worth stating.

## 13. Out of scope

Per-field or per-report permissions; groups or teams; SCIM; audit UI; password
or magic-link sign-in; per-path verb caveats in datahive.
