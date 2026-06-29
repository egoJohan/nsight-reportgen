# Staging deployment — UpCloud (plan)

Status: **plan only** — local containerized run is verified (`docker compose up`);
staging is not provisioned yet.

The app ships as two images already defined in this repo:

- **backend** (`Dockerfile.backend`) — FastAPI + the render engine, with
  LibreOffice + poppler. Runs in demo mode (self-contained on-disk store) by
  default; can be pointed at a real datahive via env.
- **frontend** (`web/Dockerfile`) — the Vite SPA built and served by nginx,
  which also reverse-proxies the API to the backend (same origin, no CORS).

Locally these run via `docker-compose.yml` (UI on `:8090`). Staging is the same
two containers on an UpCloud server, fronted by TLS.

## 1. Provision (UpCloud)

- Create a Cloud Server (Ubuntu 24.04 LTS). Sizing: rendering is LibreOffice +
  matplotlib, CPU-bound and parallel (pool of 4) — start at **2 vCPU / 4 GB**,
  scale up if first-render batches are slow.
- Add the server to a private SDN if datahive/egoHive will also be reachable.
- Attach a storage volume (or use the OS disk) for the persisted demo store
  and let the SPSS uploads live on a Docker named volume.
- Firewall (UpCloud "Firewall" or `ufw`): allow **22** (SSH, ideally
  IP-restricted), **80**, **443**. Do **not** expose the backend port.

## 2. Host setup

```bash
# on the server
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER     # re-login
```

## 3. Get the images onto the server

Two options:

- **Build on the server** (simplest for staging): `git clone` this repo and
  `docker compose build`. Heavy (LibreOffice apt + uv sync) but no registry.
- **Build in CI, push to a registry** (recommended once it stabilises): push to
  GHCR or Docker Hub; the server `docker compose pull`. Add a `deploy` job to
  `.github/workflows/ci.yml` that builds + pushes on `master`, then SSHes to the
  server and runs `docker compose pull && docker compose up -d`.

## 4. Run + TLS

Put a TLS-terminating reverse proxy in front (Caddy is the least effort — auto
Let's Encrypt). Example `Caddyfile`:

```
staging.nsight.example.com {
    reverse_proxy localhost:8090
}
```

Keep `docker-compose.yml` publishing the frontend on `127.0.0.1:8090` (loopback
only) and let Caddy (host) terminate TLS and proxy to it. Then:

```bash
docker compose up -d --build
```

A `docker-compose.staging.yml` override can pin the published port to loopback
and set `restart: always`.

## 5. Configuration / env

- **Store mode**: `NSIGHT_DEMO=1` (default) is fine for staging — self-contained,
  persisted in the `nsight-demo` volume. To use a real datahive instead, unset
  `NSIGHT_DEMO` and provide the datahive env the backend reads
  (`datahive_client_from_env`).
- **AI features (egoHive)**: slide titles + label shortening call egoHive at
  `work/egohive_creds.json` / its `base_url`. On staging that URL must be
  reachable from the backend container (same SDN, or a public URL + token).
  Without it, the app degrades gracefully to the original question text/labels
  (a 503 from `/ai/*` is caught). See [egohive-ai-dependency] in memory.
- **CORS**: not needed (single origin via nginx). If the SPA is ever served from
  a different host than the API, set `NSIGHT_CORS_ORIGINS`.
- **Fonts**: the backend image installs DejaVu + Liberation so label metrics are
  stable; if the deck must match a brand font, bake it into the image.

## 6. Persistence & backups

- Named volume `nsight-demo` holds cases/materials/reports (demo mode). Back it
  up (`docker run --rm -v nsight-demo:/d -v $PWD:/b alpine tar czf /b/demo.tgz /d`)
  or snapshot the UpCloud volume on a schedule.

## 7. Smoke test after deploy

```bash
curl -fsS https://staging.nsight.example.com/chart-types | head -c 200   # 12 chart types
# then in a browser: New case → upload a .sav → Create report → toggle a question → render
```

The repo's `web/scripts/verify-flow.mjs --url=https://staging.…` runs that flow
headlessly (ignore the AI 503 if egoHive isn't wired yet).

## Open decisions before provisioning

- Registry vs build-on-server (affects the CI deploy job).
- Demo store vs real datahive for staging.
- Whether egoHive is reachable from staging (gates the AI features).
- Domain + TLS (Caddy vs nginx+certbot).
