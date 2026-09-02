#!/usr/bin/env bash
# Deploy staging without dropping a request.
#
# `docker compose up -d --build` recreates in place: the backend stops, and for
# the six seconds it takes to come back every request in flight and every
# request made answers 502. On 2026-09-02 one deploy produced 247 of them, 245
# to a single author working in Design — and because a failed render was not
# retried across the gap, their slides stayed blank until they reopened the
# report. Deploying is the main manufacturer of the fault we spent the day
# chasing.
#
# Two hops, two answers:
#
#   caddy -> nginx    Caddy holds the connection and retries for a few seconds
#                     (lb_try_duration in deploy/Caddyfile), so the frontend
#                     container can be replaced the ordinary way and nobody
#                     downstream sees it.
#
#   nginx -> backend  There is nothing to retry TO while the only backend is
#                     restarting, so a second one is started first. nginx
#                     resolves the service name through Docker's DNS with
#                     `valid=10s` (web/nginx.conf), so it picks the new
#                     container up by itself; the old one is removed only once
#                     the new one answers /readyz.
#
# Usage:  scripts/deploy/staging.sh [--dry-run]
set -euo pipefail

HOST=${NSIGHT_STAGING_HOST:-root@94.237.12.104}
KEY=${NSIGHT_STAGING_KEY:-~/.ssh/egohive-staging}
DIR=/opt/nsight
COMPOSE="docker compose -f docker-compose.staging.yml"
DRY=${1:-}

ssh_() { ssh -i "$KEY" -o StrictHostKeyChecking=no "$HOST" "$@"; }

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

say "1/7  copying the working tree to $HOST:$DIR"
rsync -az --delete \
  --exclude='.git' --exclude='.venv' --exclude='node_modules' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='/web/dist' --exclude='/work' --exclude='/input' \
  --include='/src/reportbuilder/render/assets/nsight_default.pptx' \
  --exclude='/ui' --exclude='/chart_lab' --exclude='*.sav' --exclude='*.pptx' \
  --exclude='/.env' \
  -e "ssh -i $KEY -o StrictHostKeyChecking=no" ./ "$HOST:$DIR/"

say "2/7  building images (nothing is swapped yet)"
ssh_ "cd $DIR && $COMPOSE build backend frontend"

if [ "$DRY" = "--dry-run" ]; then say "dry run: built only, nothing swapped"; exit 0; fi

say "3/7  reloading Caddy so it rides out the frontend swap"
ssh_ "cp $DIR/deploy/Caddyfile /etc/caddy/Caddyfile 2>/dev/null || true;
      docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile" \
  || echo "  (caddy reload skipped — check deploy/Caddyfile is mounted)"

say "4/7  starting a SECOND backend on the new image, old one still serving"
OLD=$(ssh_ "cd $DIR && $COMPOSE ps -q backend | head -1")
[ -n "$OLD" ] || { echo "no running backend found; falling back to a plain up"; ssh_ "cd $DIR && $COMPOSE up -d --build"; exit 0; }
ssh_ "cd $DIR && $COMPOSE up -d --no-deps --no-recreate --scale backend=2 backend"

say "5/7  waiting for the new backend to answer /readyz"
NEW=$(ssh_ "cd $DIR && $COMPOSE ps -q backend | grep -v ${OLD:0:12} | head -1")
[ -n "$NEW" ] || { echo "could not identify the new container; leaving BOTH running"; exit 1; }
for i in $(seq 1 60); do
  # The image carries no curl, wget or python3 on PATH — the interpreter is in
  # the venv, and asking the container itself is the only way to tell the NEW
  # backend apart from the old one, which is still answering on the same name.
  if ssh_ "docker exec ${NEW:0:12} /app/.venv/bin/python -c \"import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8200/readyz', timeout=3).status==200 else 1)\"" >/dev/null 2>&1; then
    echo "  ready after ${i}s"; READY=1; break
  fi
  sleep 1
done
if [ "${READY:-}" != "1" ]; then
  echo "  the new backend never became ready — removing it, the old one keeps serving"
  ssh_ "docker rm -f ${NEW:0:12}"
  exit 1
fi

say "6/7  retiring the old backend (nginx re-resolves within 10s)"
ssh_ "docker stop -t 25 ${OLD:0:12} && docker rm ${OLD:0:12}"

say "7/7  updating the frontend IN PLACE (nginx reload, not a recreate)"
# Recreating this container is not free: it holds the published port, so it
# cannot be blue/greened, and killing it resets whatever is in flight. Caddy can
# retry a connection it never established — that is what lb_try_duration buys —
# but not a request whose connection dies mid-body, and the deploy before this
# one reset a live user's PUT that way. `nginx -s reload` starts new workers,
# lets the old ones finish what they are serving, and swaps with nothing
# dropped.
FE=$(ssh_ "cd $DIR && $COMPOSE ps -q frontend | head -1")
if [ -n "$FE" ]; then
  ssh_ "set -e
    cid=\$(docker create nsight-frontend:latest)
    rm -rf /tmp/fe-new && mkdir -p /tmp/fe-new
    docker cp \"\$cid:/usr/share/nginx/html/.\" /tmp/fe-new/
    docker cp \"\$cid:/etc/nginx/conf.d/default.conf\" /tmp/fe-new.conf
    docker rm \"\$cid\" >/dev/null
    # The assets are content-hashed, so the new ones land beside the old and any
    # page still open keeps loading the files it was built against.
    docker cp /tmp/fe-new/. ${FE:0:12}:/usr/share/nginx/html/
    docker cp /tmp/fe-new.conf ${FE:0:12}:/etc/nginx/conf.d/default.conf
    docker exec ${FE:0:12} nginx -t
    docker exec ${FE:0:12} nginx -s reload"
else
  echo "  no frontend container found; creating one"
  ssh_ "cd $DIR && $COMPOSE up -d --no-deps frontend"
fi

say "done"
ssh_ "cd $DIR && $COMPOSE ps --format '  {{.Name}}  {{.Status}}'"
