# Local setup

Local development mirrors **staging**, which is two UpCloud VMs, each
`STARTER-1xCPU-4GB`:

| Staging | Locally |
|---|---|
| `nsight-v2` — the app, 1 vCPU | backend pinned to **core 0** with `taskset` |
| `datahive-yfbceyma` — the hive, 1 vCPU | container `egohive-nsight`, `--cpus=1 --cpuset-cpus=1 --memory=4g` |

**One core each is the point, not a detail.** The render pipeline is
CPU-bound (LibreOffice → PDF → raster) and `export/_cpu.usable_cores()`
reads process *affinity*, so `taskset -c 0` makes the render pool size
itself to 1 exactly as it does on staging. Run it unpinned on a 16-core
laptop and previews are six-way parallel — every timing you measure is
then a number staging can never reproduce.

Pinning to *different* cores matters too: the app and the hive are
separate machines in staging, so they must not contend here.

## The hive — `egohive-nsight`

One container running entrance + hive + colony under s6, with its own
bundled Postgres and Qdrant (`STORAGE_SCHEME=bundled`). There is no
separate `postgres`/`qdrant` container to run; egohive handles storage
itself, and a loose one alongside it is a leftover.

Built from the **egohive** repo (`~/Projects/egoiq/egohive`, branch
`master`) — not from `egohive-datahive`, and not from the stale
`reshape/egohive` worktree nested inside it:

```bash
cd ~/Projects/egoiq/egohive
docker build -f docker/datahive.Dockerfile -t datahive:egohive .

docker run -d --name egohive-nsight --restart unless-stopped \
  --cpus=1 --cpuset-cpus=1 --memory=4g \
  --env-file <(docker inspect egohive-nsight \
      --format '{{range .Config.Env}}{{println .}}{{end}}') \
  -p 127.0.0.1:7984:7984 -p 127.0.0.1:7985:7985 \
  -v egohive-data:/var/lib/datahive \
  datahive:egohive
```

The volume `egohive-data` is the instance. Rebuilding the image is safe;
deleting that volume is not.

`:7985` is the **entrance** and the only port nSight should ever be
pointed at. `:7984` is the hive itself — reaching past the entrance
bypasses the boundary that answers readiness and gates egress.

## The app

```bash
cd ~/Projects/nsight/studio
set -a; . ~/.config/egohive/local.env; set +a   # NSIGHT_DATAHIVE_URL + _TOKEN
export NSIGHT_BOOTSTRAP_ADMINS=johan@egoiq.com
export NSIGHT_PUBLIC_URL=http://localhost:5180

setsid nohup taskset -c 0 .venv/bin/python -m uvicorn \
  reportbuilder.api.server:build_server_app --factory \
  --host 127.0.0.1 --port 8200 > /tmp/nsight-backend.log 2>&1 < /dev/null &

cd web && npm run dev      # Vite on :5180, proxies to :8200
```

## Sign in at `http://localhost:5180`, never `127.0.0.1`

There are no passwords — Google or Microsoft only. The OAuth client has
`http://localhost:5180/auth/callback/google` registered and
`http://127.0.0.1:5180/...` **not**, and `NSIGHT_PUBLIC_URL` is what
builds that `redirect_uri`. Browse to the wrong one and Google answers
`redirect_uri_mismatch`, which reads as "login is broken".

A fresh hive has no OIDC credentials, and they cannot be added through
the UI — `PUT /settings/oidc` needs an admin, and nobody can become one
without signing in first. Seed them directly:

```bash
python -c "
import json
from reportbuilder.api.deps_store import build_repository, get_auth
from reportbuilder.api.routes_settings import OIDC_KEY
repo, auth = build_repository(), get_auth()
repo.set_setting(auth, OIDC_KEY, json.load(open('$HOME/.config/egohive/backup/oidc.json')))
"
```

`NSIGHT_BOOTSTRAP_ADMINS` then promotes that address on its first
sign-in. Use **Google** for it: `identity.py` refuses to mint a new
account for an unproven email domain, and that check runs *before* the
break-glass. Microsoft only proves the domain via the optional
`xms_edov` claim, which this app registration does not send — so a
Microsoft-first sign-in to an empty hive is refused and looks like a
broken deployment.

## Verify

```bash
curl -s localhost:5180/health                    # 200
curl -s localhost:5180/auth/providers            # {"google":true,"microsoft":true}
curl -s localhost:7985/health                    # 200 — the hive

python -c "
from reportbuilder.export._cpu import usable_cores, workers_for
print('cores', usable_cores(), 'pool', workers_for(6))"   # 1 1, as staging
```

The hive should report the six `purpose` values; if `description` is
empty it is running code older than `a2bda438` and needs rebuilding:

```bash
curl -s localhost:7985/openapi.json | python -c "
import json,sys
print(json.load(sys.stdin)['components']['schemas']['AskRequest']
      ['properties']['purpose'].get('description','')[:80])"
```

## Testing against the hive staging actually runs

The hive in this setup is a locally built image and it drifts from the one the
fleet promotes — far enough that `/readyz` has answered with different FIELDS.
For anything that depends on what the hive replies (readiness, upgrades,
permissions, error shapes), bring up the verify stack beside this one:

    scripts/dev/verify_stack.sh up

It runs the staging image on its own ports and volume, leaves this stack
untouched, and throws itself away on `down`. See
[dev-verify-stack.md](dev-verify-stack.md).
