#!/usr/bin/env bash
# A local stack running the SAME hive image as staging, beside your normal one.
#
# WHY. The everyday dev hive is a locally built `datahive:local`, and it drifts:
# on 2026-09-01 it was old enough to lack `/readyz`'s build and disk fields
# entirely, so a change that depended on them looked broken locally and worked
# on staging — or, worse, the reverse. Anything about upgrades, readiness,
# permissions or the shape of what the hive answers has to be tried against the
# image staging actually runs, and the only honest way to do that is to run it.
#
# It is ISOLATED on purpose: its own container, its own volume, its own ports,
# its own backend process. Your normal stack keeps running and keeps its data.
#
#   scripts/dev/verify_stack.sh up      # bring it up, print the URLs
#   scripts/dev/verify_stack.sh status  # what is running, and what it reports
#   scripts/dev/verify_stack.sh down    # remove it, volume included
#
# Override the image to test a specific build:
#   IMAGE=ghcr.io/egoiq/egohive:sha-<git> scripts/dev/verify_stack.sh up
set -euo pipefail

# The channel the fleet promotes to staging, so `up` follows staging by default.
IMAGE="${IMAGE:-ghcr.io/egoiq/egohive:staging}"
HIVE_NAME=nsight-verify-hive
VOLUME=nsight-verify-data
HIVE_PORT=17891          # the hive itself (unpublished in production)
ENTRANCE_PORT=17892      # the boundary nSight talks to
BACKEND_PORT=8299        # a second nSight, beside your usual one on 8200
ADMIN="${ADMIN:-johan@egoiq.com}"
WORK=work/verify

here() { cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd; }
cd "$(here)"
mkdir -p "$WORK"

backend_pid() { pgrep -f "uvicorn reportbuilder.api.server.*--port $BACKEND_PORT" || true; }

up() {
  echo "image: $IMAGE"
  docker pull -q "$IMAGE" >/dev/null

  docker rm -f "$HIVE_NAME" >/dev/null 2>&1 || true
  docker volume rm "$VOLUME" >/dev/null 2>&1 || true
  docker volume create "$VOLUME" >/dev/null
  # No DATAHIVE_GIT_SHA here, deliberately: the image bakes the real one and an
  # env entry would mask it — which is exactly how a hive ended up reporting
  # "unknown" and could never satisfy the fleet's health gate.
  docker run -d --name "$HIVE_NAME" \
    -e NAME=nsight-verify -e PORT=7891 -e ENTRANCE_PORT=7892 \
    -e TIER=personal -e STORAGE_SCHEME=bundled \
    -e KMS_BACKEND=file -e KMS_PROFILE=dev -e TLS_SCHEME=off \
    -v "$VOLUME":/var/lib/datahive \
    -p 127.0.0.1:$HIVE_PORT:7891 -p 127.0.0.1:$ENTRANCE_PORT:7892 \
    "$IMAGE" >/dev/null
  echo -n "waiting for the hive (postgres init + migrations on first boot) "
  for _ in $(seq 1 60); do
    if curl -sf -m 4 "http://127.0.0.1:$ENTRANCE_PORT/readyz" 2>/dev/null | grep -q '"ok":true'; then
      echo " ready"; break
    fi
    echo -n .; sleep 5
  done

  # The credential nSight uses. Two traps, both documented in
  # docker-compose.yml and both re-learned the hard way: mint it with the
  # DEFAULT purpose (a `hive-admin` one is a MANAGEMENT credential and every
  # content path answers `management_not_content`), and `--groups owner` or
  # deletes come back asking a human for consent — which is how "delete report"
  # looks broken: the button works, the object stays.
  docker exec "$HIVE_NAME" datahive auth grant nsight-backend \
    --config /var/lib/datahive/datahive.yaml \
    --state-dir /var/lib/datahive --groups owner --expires 365d --json \
    2>/dev/null | tr -d '\r' > "$WORK/grant.json"
  python3 - "$WORK" <<'PY'
import json, re, sys
work = sys.argv[1]
m = re.search(r"\{.*\}", open(f"{work}/grant.json").read(), re.S)
open(f"{work}/token.txt", "w").write(json.loads(m.group(0))["bearer"] if m else "")
PY
  [ -s "$WORK/token.txt" ] || { echo "could not mint a token"; exit 1; }

  NSIGHT_DATAHIVE_URL="http://127.0.0.1:$ENTRANCE_PORT" \
  NSIGHT_DATAHIVE_TOKEN="$(cat "$WORK/token.txt")" \
  NSIGHT_BOOTSTRAP_ADMINS="$ADMIN" \
  NSIGHT_PUBLIC_URL="http://localhost:5180" \
  setsid nohup .venv/bin/python -m uvicorn reportbuilder.api.server:build_server_app \
    --factory --host 127.0.0.1 --port $BACKEND_PORT \
    > "$WORK/backend.log" 2>&1 < /dev/null &
  for _ in $(seq 1 40); do
    curl -sf -m 3 "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1 && break
    sleep 1
  done

  # An admin and a session, because OIDC cannot be completed headlessly and a
  # test-only bypass in the backend would be a door that then exists in
  # production too. This mints a REAL session the way a sign-in does.
  NSIGHT_DATAHIVE_URL="http://127.0.0.1:$ENTRANCE_PORT" \
  NSIGHT_DATAHIVE_TOKEN="$(cat "$WORK/token.txt")" PYTHONPATH=src \
  .venv/bin/python - "$ADMIN" <<'PY'
import sys
from reportbuilder.api.deps_store import build_repository, service_auth
from reportbuilder.auth.permissions import User
auth, repo = service_auth(), build_repository()
email = sys.argv[1]
if not any(u.email.lower() == email.lower() for u in repo.list_users(auth)):
    repo.save_user(auth, User(id="", email=email, name=email, is_admin=True))
PY
  NSIGHT_DATAHIVE_URL="http://127.0.0.1:$ENTRANCE_PORT" \
  NSIGHT_DATAHIVE_TOKEN="$(cat "$WORK/token.txt")" PYTHONPATH=src \
  .venv/bin/python scripts/e2e/mint_session.py "$ADMIN" > "$WORK/cookie.txt" 2>/dev/null
  status
}

status() {
  echo
  echo "  hive     http://127.0.0.1:$ENTRANCE_PORT/readyz"
  echo "           $(curl -s -m 5 "http://127.0.0.1:$ENTRANCE_PORT/readyz" 2>/dev/null | head -c 200)"
  echo "  backend  http://127.0.0.1:$BACKEND_PORT"
  echo "           health $(curl -s -m 5 "http://127.0.0.1:$BACKEND_PORT/health" 2>/dev/null)"
  echo "           readyz $(curl -s -m 8 "http://127.0.0.1:$BACKEND_PORT/readyz" 2>/dev/null)"
  echo "  session  $WORK/cookie.txt ($(wc -c < "$WORK/cookie.txt" 2>/dev/null || echo 0) bytes)"
  echo
  echo "  drive it:  curl -H \"Cookie: nsight_session=\$(cat $WORK/cookie.txt)\" \\"
  echo "               http://127.0.0.1:$BACKEND_PORT/cases"
  echo "  the browser still points at your NORMAL stack on :5180 / :8200."
}

down() {
  pid="$(backend_pid)"; [ -n "$pid" ] && kill $pid 2>/dev/null && echo "  backend stopped"
  docker rm -f "$HIVE_NAME" >/dev/null 2>&1 && echo "  hive removed"
  docker volume rm "$VOLUME" >/dev/null 2>&1 && echo "  volume removed"
  rm -f "$WORK/token.txt" "$WORK/cookie.txt" "$WORK/grant.json"
}

case "${1:-}" in
  up) up ;;
  down) down ;;
  status) status ;;
  *) sed -n '2,20p' "$0"; exit 2 ;;
esac
