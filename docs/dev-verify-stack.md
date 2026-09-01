# The verify stack — developing against the hive staging actually runs

`scripts/dev/verify_stack.sh up`

A second, throwaway stack beside your normal one: its own hive container, its
own volume, its own ports, its own nSight process. Your everyday stack keeps
running and keeps its data.

| | normal | verify |
|---|---|---|
| hive image | `ghcr.io/egoiq/egohive:staging` | whatever `IMAGE=` you give it |
| container | `egohive-nsight` | `nsight-verify-hive` |
| hive entrance | `127.0.0.1:7985` | `127.0.0.1:17892` |
| nSight backend | `127.0.0.1:8200` | `127.0.0.1:8299` |
| volume | `egohive-data` (your work) | `nsight-verify-data` (deleted by `down`) |
| browser | `http://localhost:5180` | none — drive it with curl or a script |

**What this is for now.** The normal stack already runs the promoted image (see
[local-setup.md](local-setup.md)), so "test against staging's hive" is the
default rather than something you have to arrange. This stack answers the other
question: *does a SPECIFIC build work* — one that is not promoted yet, one you
are about to promote, or one you are bisecting — without touching the hive that
holds your work.

```bash
IMAGE=ghcr.io/egoiq/egohive:sha-<full-git-sha> scripts/dev/verify_stack.sh up
```

It also starts from an EMPTY volume, so it is the only way to exercise first
boot: migrations on a fresh instance, an empty tenant, the very first user.

## Why this exists

The everyday hive USED to be a locally built image, and it **drifted**. On
2026-09-01 it was old enough that `/readyz` carried neither `build` nor
`disk_free_gb`, while staging's had both — so anything depending on what the
hive answers was untestable against the thing that would receive it. Twice in
one day that gap cost real time:

* a fix was verified with `build_info()` in isolation and still had to be
  trusted on staging, because nothing local could run the same image;
* a hive was found reporting `git_sha: "unknown"`, which no local stack could
  have reproduced, and which silently blocks the fleet's health gate.

That is why the normal stack was moved onto the promoted image the same day.
This one remains for the builds that are NOT promoted.

## What it is good for

Try anything that involves the hive itself rather than nSight's own logic:

* **login and sessions** — a real session is minted the way a sign-in does
  (`scripts/e2e/mint_session.py`); OIDC cannot be completed headlessly, and a
  test-only bypass in the backend would be a door that then exists in production
* **permissions** — a user with no grants must see empty lists, not errors
* **deletes** — they must not come back asking a human for consent
* **readiness and upgrade behaviour** — stop the hive and watch nSight's
  maintenance screen; start it and watch the screen clear itself
* **a fresh instance** — first boot, migrations, an empty tenant

Verified end to end on 2026-09-01 against `sha-78040712`: sign-in path,
`/auth/me`, empty-but-successful listings for a user with no data, customer and
case creation, a 5.7 MB SPSS upload, the sensitive-terms gate, report create /
lock / save / delete.

## Things that will bite you

Each of these cost an attempt before it was written down.

* **`HOSTING` is `self_hosted`**, not `self`. `datahive init` refuses the short
  form and the container sits there with nothing listening.
* **Mint the token with the DEFAULT purpose.** `--purpose hive-admin` looks
  stronger and is wrong: it is a MANAGEMENT credential, so every content path
  answers `management_not_content` — the backend starts, serves, and fails on
  the first object it touches.
* **`--groups owner` is required.** Without it deletes need human consent, which
  is how "delete report" looks broken: the button works, the object stays.
* **Never set `DATAHIVE_GIT_SHA`.** The image bakes the real one; an env entry
  masks it, `/readyz` then reports `unknown`, and the fleet's health gate — which
  compares that field to the sha it deployed — can never pass. This is not
  hypothetical: it is how the staging hive ended up ungateable.
* **First boot takes ~40s** (postgres init, migrations). `up` waits for it.
* **The config lives in the VOLUME, not the environment.** A container recreated
  against an existing volume needs no init variables; a fresh volume needs them
  all.

## Testing a specific build

```bash
IMAGE=ghcr.io/egoiq/egohive:sha-<full-git-sha> scripts/dev/verify_stack.sh up
```

Useful before a fleet promote: run the exact image the promote would deploy,
against a real nSight, before any hive serving real work is touched.

## Cleaning up

```bash
scripts/dev/verify_stack.sh down     # container, volume and backend all go
```

The volume is deleted. Nothing in the verify stack is meant to survive.
