# UpCloud Cost Reduction & Pre-Revenue Right-Sizing — Design Spec

**Status:** Draft v2 (migration ~2 boxes in; revised after 3-way adversarial review)
**Owner:** Johan
**Goal:** Cut the UpCloud bill from a pre-restructure ~€188/mo (~€6.2/day) to ~€61/mo running (~€2.0/day; ~€56 with staging stopped) by right-sizing every VM to the STARTER (standard-storage) tier, self-hosting Postgres in-VM for the apps that need it, splitting the DataHive fleet, and making staging pay-per-use — while keeping every component on its own VM so any one can scale up on demand once there is a paying customer.

---

## 1. Why

Zero customers today. Every resource is provisioned as if serving production load: general-purpose / DEV plans on **maxiops** (premium-IOPS) storage, plus a **managed** Postgres. That is production-grade spend for idle staging-grade workloads. The tenant-isolation rules that would normally forbid consolidation do not yet apply — there is no customer data to protect. So: shrink each box to the floor now, keep them separate for clean scale-up later, and reverse the collapse the day the first customer signs.

## 2. Principles & constraints (hard requirements)

Johan's explicit rules; every task inherits them.

1. **Components stay on separate VMs** — do NOT collapse to 1–2 shared boxes. Each box is shrunk to minimum but isolated.
2. **No managed or shared Postgres** — each app that needs a database self-hosts it as a container **in its own VM**. (nsight needs no DB: it uses a local file store — see §5.2.)
3. **nsight stays on its own VM** — never folded onto an egoHive box.
4. **DataHive fleet is split** — the general/shared fleet host is separate from egoiq's dedicated DataHive.
5. **egoHive staging is started on demand** — kept stopped (or torn down to a template) when not in use.
6. **KeyHive/OpenBao is removed** from the current egoHive stack (app = api + scheduler + Postgres). Production may still run KeyHive because prod has fallen behind; the prod rebuild brings it up to the current KeyHive-less architecture — **including migrating every secret KeyHive holds, not just the DB DSN** (§7 Phase 4).
7. **Prod does not need maxiops** — standard storage is acceptable for prod.
8. **Backup before any move; never risk data loss or IPR exposure to third parties.**
9. **Scale up on demand later** — sizes are deliberate floors; upsizing is a 2-minute `modify`.

## 3. Billing model — verified facts (UpCloud `fi-hel`, price API 2026-07-12)

- **€/mo = plan price (credits/hour) × 7.3** (730 h/mo ÷ 100 credits-per-€). Verified against the €31–32 Johan saw for a `2xCPU-4GB` in the console.
- **`part_of_plan=yes` disks are bundled** into the plan price — not additive. **Two** normal disks are additive (`part_of_plan=""`): `terraform-egohive-coolify-disk` (60 GB maxiops) and `nsight-staging-OS` (80 GB maxiops, on the retiring box). All other VMs' disks are bundled.
- **Storage tiers €/GB/mo:** maxiops 0.226 · standard 0.086 · backup 0.057.
- **STARTER = budget tier, standard storage, small bundled disk.** Same vCPU/RAM as general-purpose; cheaper via the storage tier + lower CPU priority. Fine for idle workloads.
- **Resize direction:** upsizing is `stop → upctl server modify --plan … → start` (~2 min); disks only **grow**. Changing storage tier (maxiops↔standard) or shrinking a disk requires a **rebuild** (backup first).
- **Plan prices used in this doc (€/mo, all-in incl. bundled storage):**
  STARTER: `1xCPU-1GB` 3.26 · `1xCPU-2GB` 6.52 · `1xCPU-4GB` 10.86 · `2xCPU-2GB` 8.69 · `2xCPU-4GB` 13.04 · `2xCPU-8GB` 19.55.
  Current-tier (for §4): `DEV-2xCPU-4GB` 19.55 · general `2xCPU-4GB` 32.59 · `2xCPU-2GB` 21.73 · `1xCPU-1GB` 8.15.
  Managed PG: `1x1xCPU-1GB-10GB` 8.11 · `1x1xCPU-2GB-25GB` 30.42.
  Floating IPv4: 3.51 each (a server's first/primary public IP is bundled/free; extra floating IPs bill).
- **Stopped-server billing — OPEN (§9-Q1):** whether a stopped server bills storage-only or full plan decides staging's idle cost.

## 4. Current state (post-restructure, transitional — 2026-07-12)

This is the **elevated transitional bill**: `nsight-v2` + `dh-egoiq` run alongside the not-yet-retired old boxes.

| # | Resource | Plan / spec | Storage | State | €/mo | Notes |
|---|---|---|---|---|---|---|
| 1 | egohive-prod | 2xCPU-4GB | 25 GB maxiops (bundled) | started | 32.59 | app + scheduler; DSN → managed pg |
| 2 | egohive-prod-pg | managed `1x1xCPU-2GB-25GB` | 25 GB | running | 30.42 | LIVE: `egohive` db, connections from 85.9.223.41 |
| 3 | datahive-fleet-1 | 2xCPU-2GB | 60 GB maxiops (bundled) | started | 21.73 | shared + egoiq + wildcard hives + control-plane + caddy |
| 4 | egohive-coolify | DEV-2xCPU-4GB | 60 GB **maxiops (additive)** | started | 33.13 | 19.55 plan + 13.58 disk; Coolify + staging platform |
| 5 | egohive-headscale | 1xCPU-1GB | 25 GB maxiops (bundled) | started | 8.15 | VPN mesh coordinator |
| 6 | nsight-staging | 1xCPU-2GB | 80 GB **maxiops (additive)** | **stopped** | ~18.10 | old nsight box; retiring after nsight-v2 verified |
| 7 | **nsight-v2** ✓ | STARTER-1xCPU-4GB | 30 GB standard | started | 10.86 | NEW — matches target |
| 8 | **dh-egoiq** ✓ | STARTER-1xCPU-2GB | 20 GB standard | started | 6.52 | NEW — matches target |
| 9 | pre-scaledown-* ×7 | — | 305 GB backup tier | online | 17.37 | see §4.1 |
| 10 | datahive-backups | managed object storage | — | started | ~5.00 | datahive backup bucket |
| 11 | floating IPs ×2 | prod (81.27.99.132) + nsight (94.237.12.104) | — | — | 7.02 | |
| | | | | **transitional total** | **≈ 190.9** | ≈ €6.3/day |

**Baselines:** pre-restructure (before rows 7–8 existed, old nsight running) ≈ **€188/mo**; current transitional ≈ **€190.9/mo** (overlap). Target (§5) is measured against the ~€188–191 baseline.

### 4.1 The 7 `pre-scaledown-*` snapshots (map to source box, for rollback)
`egohive-staging-app` (30 GB) · `egohive-coolify` (60 GB) · `nsight-staging` (80 GB) · `egohive-headscale` (25 GB) · `egohive-staging` (25 GB) · `egohive-prod` (25 GB) · `datahive-fleet-1` (60 GB). Backup tier, taken 2026-07-11. `pre-scaledown-nsight-staging` is the Phase 1 rollback; `pre-scaledown-datahive-fleet-1` backs Phase 2.

## 5. Target architecture

Six VMs, all STARTER/standard; PG in-VM for apps that need one; nsight separate.

| VM | Sole role | Domains | PG | Plan | Floating IP | €/mo |
|---|---|---|---|---|---|---|
| **egohive-prod** | api + scheduler | `api`/`datahive.egohive.ai` | container in-VM (folded from managed) | STARTER-1xCPU-2GB | **yes** (reuse prod FIP) | 6.52 |
| **egohive-staging** | api + scheduler (**on demand**) | `staging-*.egohive.ai` | container in-VM | STARTER-1xCPU-2GB | no (DNS on start) | 6.52 / ~1.7 stopped |
| **egohive-ops** | Coolify + headscale | `coolify`/`headscale.egohive.ai` | Coolify's own pg container | STARTER-2xCPU-2GB | no (primary IP + DNS) | 8.69 |
| **datahive-fleet** | shared + wildcard hives | `shared`/`*.hives.egohive.ai` | container in-VM (if the DataHive version needs one — §9-Q3) | STARTER-1xCPU-2GB | **yes** (new FIP for clean cutover) | 6.52 |
| **dh-egoiq** ✓ | egoiq's dedicated hive | `egoiq.hives.egohive.ai` | container in-VM (if needed) | STARTER-1xCPU-2GB | no (primary IP + DNS) | 6.52 |
| **nsight-v2** ✓ | nsight FE + BE | `nsight.egohive.ai` | none (local file store) | STARTER-1xCPU-4GB | **yes** (existing nsight FIP) | 10.86 |
| object storage | datahive-backups | — | — | — | — | 5.00 |
| floating IPs | prod + nsight + fleet = **3 × 3.51** | — | — | — | — | 10.53 |

**Target total: ~€61.2/mo running · ~€56.4/mo with staging stopped (~€1.85–2.0/day).** Down from ~€188–191/mo (€6.2–6.3/day) — a **~68–71% cut**.

- **Optional −€7.02:** drop the nsight + fleet FIPs and update their DNS on the (rare) rebuild instead of remapping a FIP → target ~€54/mo, at the cost of DNS-propagation downtime during a future rebuild. Prod keeps its FIP regardless.

### 5.1 Sizing rationale
- **prod / staging / fleet / egoiq → 1xCPU-2GB (€6.52):** the KeyHive-less egoHive stack (api + scheduler + a Postgres container) idles ~600–800 MB; a single DataHive instance + small PG is lighter. 2 GB gives headroom at idle; 1 core is right at load 0.00. Upsize in 2 min if a deploy/migration needs more.
- **ops → 2xCPU-2GB (€8.69):** exactly Coolify's documented minimum (2 vCPU / 2 GB / 30 GB); headscale rides along in ~100 MB.
- **nsight-v2 → 1xCPU-4GB (€10.86):** 1 core (slower sequential matplotlib render, acceptable pre-revenue), 4 GB for report-rendering headroom.

### 5.2 nsight ↔ egoHive coupling (verified 2026-07-14, live env on nsight-v2)
nsight is **decoupled from egoHive**: `NSIGHT_DATAHIVE_URL` unset → local file store at `/data/demo-store`; `EGOHIVE_*` unset → AI title/label agent not wired (deterministic fallback). **Consequence:** rebuilding/retiring any egoHive box cannot break nsight. If AI-generated titles are wanted back, set `EGOHIVE_BASE_URL/ENDPOINT_ID/ENDPOINT_KEY` on the nsight box pointing at a live egoHive product endpoint (separate task, out of scope here).

## 6. Per-resource disposition (every §4 row → action → target)

| Current (§4 row) | Action | Target | Access |
|---|---|---|---|
| nsight-v2 (7) | verify serving + **data-parity gate** (case/file counts vs old box) | keep | staging key |
| dh-egoiq (8) | verify egoiq hive serves `egoiq.hives.egohive.ai` | keep | staging key |
| nsight-staging (6) | after Phase 0 gate: delete server **+ 80 GB maxiops disk** | gone | upctl |
| datahive-fleet-1 (3) | rebuild → STARTER-1xCPU-2GB standard, shared+wildcard only (egoiq already split) | datahive-fleet | staging key + DNS |
| egohive-coolify (4) | **Terraform:** plan→STARTER-2xCPU-2GB, disk maxiops→standard | egohive-ops (headscale added in Phase 5) | IaC + staging key |
| egohive-headscale (5) | **Phase 5 only:** migrate state into ops, retire VM | folded into ops | IaC + DNS |
| egohive-prod (1) | rebuild → STARTER-1xCPU-2GB standard + local pg container; FIP remap | egohive-prod | **prod (mesh) + IaC** |
| egohive-prod-pg (2) | fold into prod's container; verify; delete managed; remove from IaC | gone | **prod (mesh) + upctl + IaC** |
| pre-scaledown-* ×7 (9) | delete after all rebuilds pass their bake window | gone | upctl |
| datahive-backups (10) | keep | keep | — |
| floating IP prod (11) | remap to rebuilt prod box | kept | upctl |
| floating IP nsight (11) | **keep** — remains on nsight-v2 | kept | upctl |
| (new) | create FIP for datahive-fleet cutover | kept | upctl |
| (none) | create `egohive-staging` on demand, keep stopped/template | egohive-staging | staging key |

## 7. Migration sequencing (phased, reversible, backup-first, low-risk first)

**Pre-flight (once, before any change):** enumerate exactly which resources OpenTofu owns (`tofu state list` in `egoHive-iac/deploy/iac`). Any box mutated by hand via `upctl` (nsight-staging, datahive-fleet-1) that tofu owns must be `state rm`'d/imported first so a later `apply` doesn't recreate/destroy it (§9-Q4). Lower DNS TTLs (~24 h ahead) for every record that will move: `*.hives`, `nsight`, `api`/`datahive`, `headscale`.

**Phase 0 — verify the two new boxes (no risk).**
Confirm `nsight-v2` serves `nsight.egohive.ai` **and passes a data-parity gate** — case/material/report and `/data/demo-store` file counts match the old box, not merely "UI loads." Confirm `dh-egoiq` serves the egoiq hive. Gate must pass before retiring predecessors.

**Phase 1 — retire old nsight (low).**
Delete stopped `nsight-staging` server **and its 80 GB maxiops disk** (~€18/mo). Rollback: `pre-scaledown-nsight-staging` snapshot (kept until Phase 6).

**Phase 2 — rebuild datahive-fleet-1 (low–medium).**
Snapshot disk. Build STARTER-1xCPU-2GB standard box; restore `/var/lib/datahive` + `/opt/controlplane` keys for shared+wildcard (egoiq already on `dh-egoiq`). **Wildcard TLS:** `*.hives.egohive.ai` uses ACME **DNS-01**, so copy the DNS-provider API creds **and** the existing cert/key to the new box before cutover (a floating-IP remap does NOT re-issue a wildcard, and blind retries hit Let's Encrypt's 5/week limit). Cutover: **attach the new FIP to the OLD box first**, repoint `*.hives` DNS to the FIP while the old box still serves, then remap the FIP to the new box. Data-parity gate (hive tenant list). Keep old box stopped for rollback.

**Phase 3 — coolify → ops resize via Terraform (medium). Headscale untouched.**
In `egoHive-iac/deploy/iac`: coolify VM plan → STARTER-2xCPU-2GB, disk tier → standard. `tofu plan` → reconcile drift → `apply`. **Do not fold headscale yet** — the mesh must stay intact for Phase 4. Accept slower Coolify builds on standard storage.

**Phase 4 — prod rebuild + prod-pg fold-in, one maintenance window (highest). Needs prod (mesh) access — §8.**
1. **Backup:** `pg_dumpall --globals-only` (roles + passwords) **and** `pg_dump` of `egohive`; snapshot prod disk; push copies to object storage. Verify the required extensions exist in the `postgres:15` image.
2. **Confirm the live stack** on the box (is KeyHive still running? where is `DATABASE_URL` actually set?) — NOT the stale repo compose (§9-Q2). **Inventory every secret KeyHive/OpenBao serves** (DSN, encryption/signing keys, provider keys) and stage them into `.env.prod`.
3. Build STARTER-1xCPU-2GB standard prod box; run local `postgres:15` (real password, loopback-bound); load globals then the `egohive` dump; restore role passwords/grants; verify row counts + `max(updated_at)`.
4. **Quiesce & final sync:** put the app in maintenance / stop `egohive-api` + `egohive-scheduler` so the managed DB stops taking writes, take a **final delta dump**, load it — this closes the write-gap between the initial dump and cutover. Confirm no new managed writes after the freeze.
5. Point `DATABASE_URL`/`DATABASE_URL_SYSTEM` at the local container; deploy the current (KeyHive-less) stack; run `egohive-migrate`; verify api + datahive health.
6. Remap the prod FIP to the new box (same public IP → no cert re-issue).
7. Add a `pg_dump` → object-storage backup cron and **prove it produces at least one successfully test-restored backup** before step 8.
8. Only after a **48–72 h bake** with app healthy and zero managed connections: disable `termination_protection`, delete managed `egohive-prod-pg`, remove it from the IaC.
Rollback ≤ step 6: remap the FIP back to the **old prod box** (kept stopped, not deleted, until Phase 6) — that restores the old stack + managed DB together. A bare DSN flip is not a valid rollback once `egohive-migrate` has run against the container.

**Phase 5 — fold headscale into ops (medium; after prod is safely migrated).**
Migrate headscale's **server private key + node/preauth DB** onto the ops box (not just a DNS repoint), run it behind ops' proxy. Keep the **old headscale VM running in parallel** until every node — **including the rebuilt prod box** — has reconnected to the new coordinator; then retire the old VM. Explicit gate: "prod + all nodes mesh-reachable via new headscale" before deleting the old headscale VM.

**Phase 6 — cleanup (low).**
After all rebuilds pass their bake windows: delete the 7 `pre-scaledown-*` snapshots (~€17/mo). Create `egohive-staging` on demand per §9-Q1's resolution (stopped VM or template) with its start runbook (deploy code, issue `staging-*.egohive.ai` cert, point DNS).

## 8. Access reality

- **Reachable from Johan's machine** (`~/.ssh/egohive-staging`): nsight-v2, dh-egoiq, datahive-fleet-1, coolify, headscale, nsight-staging.
- **Prod is firewalled** — port 22 mesh-only, no tailscale client on the machine; key `~/.ssh/egohive-prod`. Phase 4 steps on the prod VM need Johan to run the handed-over commands (`!` in-session / `egoctl`) or provisioned mesh access. The managed prod-pg's **public** endpoint is reachable for read-only backup/verify from Johan's machine.
- **Live IaC:** `~/egoiq-split/egoHive-iac/deploy/iac` (`environments/prod.tfvars`, `staging.tfvars`) — OpenTofu. The deploy compose in `egoHive-tofu/deploy` is **stale** (shows KeyHive + points DB at a local container while live prod uses the managed DB) — confirm from the running box, never from that file.

## 9. Open questions / verify before the affected phase

- **Q1 (Phase 6, staging cost + buildability):** Does UpCloud bill a **stopped** server storage-only (→ keep-stopped, ~€1.7/mo) or full plan (→ delete + recreate-from-template)? Resolve first; it decides staging's cost AND its start runbook.
- **Q2 (Phase 4):** Live prod stack — KeyHive still running? Where is the real `DATABASE_URL` and what other secrets does KeyHive serve? Confirm on the box.
- **Q3 (Phases 2/5, §5):** Does the current DataHive version use Postgres or embedded `/var/lib/datahive` state? Determines whether fleet/egoiq need a PG container ("in-VM PG" applies only if there is a DB).
- **Q4 (pre-flight/3/4):** OpenTofu state vs reality — IaC's last commit predates the 2026-07-11 scaledown. `tofu plan` + reconcile (import/`state rm`) before any hand-delete or `apply`.
- **Q5 (Phase 4 alt):** Lower-risk alternative to folding: **downsize** managed pg to `1x1xCPU-1GB-10GB` (~€8/mo, saves ~€22, keeps managed backups/HA) — verify UpCloud allows the 25→10 GB storage downgrade.

## 10. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Write-gap between prod dump and cutover | silent prod data loss | Phase 4 step 4 quiesce + final delta dump; verify `max(updated_at)` |
| Headscale move severs prod mesh access | can't reach prod for Phase 4 or rollback | headscale folded **after** prod (Phase 5); migrate key+DB; parallel-run old until all nodes incl. prod reconnect |
| Dropping KeyHive loses secrets beyond the DSN | app broken / encrypted data inaccessible | Phase 4 step 2 inventories & migrates **all** OpenBao secrets first |
| Wildcard cert not re-issued on cutover | `*.hives` TLS breaks; LE rate-limit | copy DNS-01 creds + existing cert/key to new fleet box before cutover |
| `pg_dump` omits roles/grants/extensions | restore fails / auth broken | `pg_dumpall --globals-only`; set role passwords; verify extensions in image |
| Managed pg deleted before new backups proven | no recoverable backup | test-restore ≥1 object-storage backup before deletion |
| OpenTofu drift → `apply` recreates/destroys a live box | outage | pre-flight `state list` + reconcile before any apply |
| Trusting the stale prod compose | wrong DSN/KeyHive assumptions | confirm live stack on the box |
| IP/DNS cutover (fleet) | hive unreachable | attach FIP to **old** box first; lower TTL 24 h ahead; remap after |
| STARTER RAM floor too small | OOM on deploy/migration | 2 GB headroom for KeyHive-less stack; upsize in 2 min |
| Standard storage IOPS (prod DB, Coolify builds) | slower DB/builds | acceptable pre-revenue; maxiops re-attainable via rebuild if a customer needs it |
| Deleting snapshots / old prod box too early | lose rollback | delete only after 48–72 h bake per box (Phase 6) |

## 11. Verification / acceptance criteria

**Per-box gate before retiring its predecessor:** service answers on its domain **and** a data-parity check passes (nsight: case/file counts; hives: tenant list; prod: `egohive` row counts + `max(updated_at)` match; ops: Coolify UI + staging apps up; headscale: every node incl. prod reconnected). **Prod fold-in:** row counts match pre/post, new writes land in the container, managed pg shows **zero app connections** before deletion, and ≥1 object-storage backup has been test-restored. **Cost:** `upctl` inventory reduced to §5; run-rate ≈ €61/mo (≈ €56 staging-stopped).

## 12. Out of scope

- Dropping Coolify (deploy staging via `egoctl`+compose) — a workflow change, deferred.
- Re-wiring nsight's `EGOHIVE_*` AI-title integration (separate task, §5.2).
- nsight application/code changes; prod compute below 1xCPU-2GB; prod HA.
- Re-isolating the DataHive fleet / prod onto dedicated bigger boxes — that is the **scale-up-on-demand** path for the first customer, not this pre-revenue collapse.
