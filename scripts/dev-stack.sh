#!/usr/bin/env bash
# The full local stack: datahive + egohive + nSight backend + nSight UI.
#
#   scripts/dev-stack.sh status    what is up, and on which port
#   scripts/dev-stack.sh up        start whatever is down
#   scripts/dev-stack.sh down      stop the parts this script started
#
# egohive runs as a docker container and is NOT started here — it is shared
# with other projects, so stopping it would break them.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DH_REPO="${NSIGHT_DATAHIVE_REPO:-$HOME/Projects/egoiq/egohive/egohive-datahive}"
DH_STATE="${NSIGHT_DATAHIVE_STATE:-$HOME/.local/share/datahive/nsight-dev}"
DH_PORT=7910
EH_PORT=8000
API_PORT=8200
# 5173 is datahive's OWN admin SPA (egohive-datahive/ui-spa), which is usually
# already running and prompts for an admin macaroon. nSight pins its own port so
# the two are never confused.
UI_PORT=5180

code() { curl -sS -m 4 -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo 000; }
up()   { [ "$(code "$1")" = "200" ]; }

# A 200 only proves SOMETHING answers. Several other services live on nearby
# ports, so identify the service before calling it ours.
ui_is_nsight() { curl -sS -m 4 "http://127.0.0.1:$UI_PORT/" 2>/dev/null | grep -q "nSight Studio"; }
ui_state() {
  case "$(code "http://127.0.0.1:$UI_PORT/")" in
    200) ui_is_nsight && echo "200" || echo "FOREIGN" ;;
    *)   echo "down" ;;
  esac
}

status() {
  printf '%-24s %-6s %s\n' SERVICE HTTP URL
  printf '%-24s %-6s %s\n' "datahive (nsight-dev)" "$(code http://127.0.0.1:$DH_PORT/healthz)" "http://127.0.0.1:$DH_PORT"
  printf '%-24s %-6s %s\n' "egohive"               "$(code http://127.0.0.1:$EH_PORT/health)"  "http://127.0.0.1:$EH_PORT"
  printf '%-24s %-6s %s\n' "nSight backend"        "$(code http://127.0.0.1:$API_PORT/health)" "http://127.0.0.1:$API_PORT"
  printf '%-24s %-6s %s\n' "nSight UI"             "$(ui_state)"                               "http://localhost:$UI_PORT"
  if [ "$(ui_state)" = "FOREIGN" ]; then
    echo "  !! something else is on $UI_PORT — not nSight Studio"
  fi
}

start_datahive() {
  up "http://127.0.0.1:$DH_PORT/healthz" && { echo "datahive already up"; return; }
  ( cd "$DH_REPO" && nohup .venv/bin/datahive serve \
      --config "$DH_STATE/datahive.yaml" --state-dir "$DH_STATE" \
      > "$DH_STATE/server.log" 2>&1 & echo $! > "$DH_STATE/server.pid" )
  echo "datahive starting (pid $(cat "$DH_STATE/server.pid"))"
}

start_backend() {
  up "http://127.0.0.1:$API_PORT/health" && { echo "backend already up"; return; }
  local token
  # bearer_admin, not bearer: nSight owns this hive, and datahive gates
  # destructive operations behind an admin approval. Without owner authority
  # every "poista tutkimus" comes back needing consent that only an admin can
  # give — which is how deletion looked broken to users.
  token=$(python3 -c "import json;d=json.load(open('$ROOT/work/datahive_creds.json'));print(d.get('bearer_admin') or d['bearer'])") || {
    echo "no work/datahive_creds.json — mint one with 'datahive auth grant'"; return 1; }
  # NSIGHT_DEMO keeps the legacy case/material/report routes on the JSON store
  # while the new customer routes go to datahive. Both run side by side until
  # the call sites finish moving.
  ( cd "$ROOT" && NSIGHT_DEMO=1 \
      NSIGHT_DATAHIVE_URL="http://127.0.0.1:$DH_PORT" \
      NSIGHT_DATAHIVE_TOKEN="$token" \
      NSIGHT_HOST=127.0.0.1 NSIGHT_PORT=$API_PORT PYTHONPATH=src \
      nohup .venv/bin/python -m reportbuilder.api.server \
      > work/backend-dev.log 2>&1 & echo $! > work/backend-dev.pid )
  echo "backend starting (pid $(cat "$ROOT/work/backend-dev.pid"))"
}

start_ui() {
  ui_is_nsight && { echo "UI already up"; return; }
  [ "$(code "http://127.0.0.1:$UI_PORT/")" = "200" ] && {
    echo "port $UI_PORT is taken by something that is not nSight — refusing to start"; return 1; }
  # --strictPort: without it vite silently walks to the next free port and the
  # UI ends up somewhere nobody is looking.
  ( cd "$ROOT/web" && nohup npx vite --port $UI_PORT --strictPort \
      > "$ROOT/work/ui-dev.log" 2>&1 & echo $! > "$ROOT/work/ui-dev.pid" )
  echo "UI starting (pid $(cat "$ROOT/work/ui-dev.pid"))"
}

case "${1:-status}" in
  status) status ;;
  up)
    up "http://127.0.0.1:$EH_PORT/health" || echo "WARNING: egohive is down — AI features will 503. Start its container."
    start_datahive; start_backend; start_ui; sleep 8; echo; status ;;
  down)
    for p in "$DH_STATE/server.pid" "$ROOT/work/backend-dev.pid" "$ROOT/work/ui-dev.pid"; do
      [ -f "$p" ] && kill "$(cat "$p")" 2>/dev/null && echo "stopped $(basename "$(dirname "$p")")/$(basename "$p")"
      rm -f "$p"
    done
    echo "egohive left running (shared with other projects)" ;;
  *) echo "usage: $0 {status|up|down}"; exit 1 ;;
esac
