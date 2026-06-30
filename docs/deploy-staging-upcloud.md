# Staging deployment — nSight Studio on UpCloud

Status: **LIVE — https://nsight.egohive.ai** (Let's Encrypt TLS, http→https).

## Live deployment (record)

| | |
|---|---|
| URL | **https://nsight.egohive.ai** |
| Server | `nsight-staging` UUID `00f2cb37-f49c-4f4f-8bc1-bf22ac4e9976`, **fi-hel2**, 2xCPU-4GB, Ubuntu 24.04 |
| Public IP | `85.9.223.140` (main); **floating `94.237.12.104`** (DNS target, on eth0 via `/etc/netplan/99-floating-ip.yaml`) |
| Utility IP | `10.6.17.230` (fi-hel2 — same zone as the egoHive/datahive fleet) |
| Code | rsync'd from the local working tree to `/opt/nsight` (GitHub master is behind — never pushed; deploy from local) |
| Run | `cd /opt/nsight && docker compose -f docker-compose.staging.yml up -d --build` |
| TLS | Caddy (host) `/etc/caddy/Caddyfile` (= `deploy/Caddyfile`) → loopback `:8090` |
| egoHive/AI | **pending** — creds point to `localhost:8000`; egoHive runs on the egoHive boxes, not nsight. AI/chat degrade to 503 until egoHive is reachable (see below). |

Redeploy (from the local machine):
```bash
rsync -az --delete \
  --exclude='.git' --exclude='.venv' --exclude='node_modules' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='/web/dist' --exclude='/work' --exclude='/input' \
  --exclude='/ui' --exclude='/chart_lab' --exclude='*.sav' --exclude='*.pptx' \
  -e 'ssh -i ~/.ssh/egohive-staging' ./ root@85.9.223.140:/opt/nsight/
ssh -i ~/.ssh/egohive-staging root@85.9.223.140 \
  'cd /opt/nsight && docker compose -f docker-compose.staging.yml up -d --build'
```
NOTE on rsync excludes: anchor host-only dirs with a leading slash (`/ui`, `/input`)
— an un-anchored `ui` also matches `web/src/components/ui/` and breaks the build.

---

The notes below are the original provisioning runbook (kept for reference / rebuilds).

Status: **artifacts ready.** The production-style images build green and the
containerized stack runs locally (`docker compose up`, UI on :8090, API proxied).

**Locked decisions (this round):**

| Decision | Choice |
|---|---|
| Image delivery | **Build on the server** (prototype phase — no CI/registry yet) |
| Store mode | **Demo store** (`NSIGHT_DEMO=1`, persisted in the `nsight-demo` volume) |
| egoHive / AI | **Wired** — creds mounted into the backend (titles, themes, chat work) |
| Domain + TLS | **`nsight.egohive.ai`** (DNS at Gandi) + **Caddy** auto-TLS |

The app is two containers (see `docker-compose.staging.yml`):
- **backend** (`Dockerfile.backend`) — FastAPI + render engine (LibreOffice +
  poppler + fonts). Demo store on a named volume; egoHive creds mounted in.
- **frontend** (`web/Dockerfile`) — Vite SPA built + served by nginx, which
  reverse-proxies the API to the backend (same origin, no CORS). Published on
  **127.0.0.1:8090** (loopback) so only the host's Caddy can reach it.

---

## 0. DNS (Gandi) — do this first

Add an **A record** for the host:

```
nsight.egohive.ai.   A   <server public IP>
```

(Set a short TTL, e.g. 300s, while provisioning.) Caddy can't obtain a TLS cert
until this resolves.

## 1. Provision (UpCloud)

- Cloud Server, **Ubuntu 24.04 LTS**, **2 vCPU / 4 GB** (rendering is LibreOffice
  + matplotlib, CPU-bound, pool of 4 — scale up if first-render batches lag).
- Firewall (`ufw` or UpCloud Firewall): allow **22** (SSH, ideally IP-restricted),
  **80**, **443**. Do **NOT** expose 8090/8200 publicly (loopback only).
- If egoHive/datahive live on a private SDN, attach the server to it so the
  backend can reach egoHive's `base_url`.

## 2. Host setup

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER     # re-login after this
# Caddy (official repo):
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

## 3. Get the code + secrets onto the server

```bash
git clone <this repo> nsight && cd nsight
```

The egoHive credentials are **NOT in git** (`work/` is gitignored). Copy them
from a trusted machine (they contain `base_url` + `endpoint_id`):

```bash
# from your laptop:
scp work/egohive_creds.json <user>@<server>:~/nsight/work/egohive_creds.json
```

Without this file the app still runs — AI endpoints (`/ai/*`, `/chat`) just
return 503 and the UI falls back to question text/labels.

## 4. Run the stack

```bash
docker compose -f docker-compose.staging.yml up -d --build
# verify locally on the box:
curl -fsS http://127.0.0.1:8090/chart-types | head -c 80   # 12 chart types
```

## 5. TLS + domain (Caddy)

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy        # obtains the Let's Encrypt cert for the domain
```

## 6. Smoke test

```bash
curl -fsS https://nsight.egohive.ai/chart-types | head -c 80
node web/scripts/verify-flow.mjs --url=https://nsight.egohive.ai   # headless: upload → report → render
```

Then in a browser: **New case → upload a .sav → Create report** (demographics
land first; batteries default to stacked) **→ render/download**, and try the
**Chat** button (top-right) — it answers from the data via egoHive.

## 7. Updates (redeploy)

```bash
cd ~/nsight && git pull && docker compose -f docker-compose.staging.yml up -d --build
```

## 8. Persistence & backups

The `nsight-demo` named volume holds cases/materials/reports:

```bash
docker run --rm -v nsight-demo:/d -v $PWD:/b alpine tar czf /b/demo-backup.tgz /d
```

(or snapshot the UpCloud volume on a schedule).

## Notes / gotchas

- **Concurrency**: the demo store is thread-safe within one process but
  single-process — run **one** backend container (the compose does). Do not add
  `--workers`. (See the multi-user analysis in the session notes.)
- **egoHive reachability**: the backend container must reach the `base_url` in
  `egohive_creds.json`. If it's on a private SDN, the server must be on it.
- **Fonts**: the backend image bakes DejaVu + Liberation for stable label
  metrics; add a brand font to `Dockerfile.backend` if the deck must match one.
- **First render is slow**: LibreOffice boots ~2.4 s on the first conversion per
  worker; subsequent renders are faster.
