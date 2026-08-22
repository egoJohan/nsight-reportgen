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
# nsight-local, not nsight-dev: the old instance shared the `datahive` database
# on :5433 with other projects, and one of their migrations emptied it — every
# table gone. This one has its own Postgres (docker-compose.datahive.yml,
# port 5434) and its own Qdrant, so nothing outside this repo can reset it.
DH_STATE="${NSIGHT_DATAHIVE_STATE:-$HOME/.local/share/datahive/nsight-local}"
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
  # Its backing services first — the hive will not start without them.
  ( cd "$ROOT" && docker compose -f docker-compose.datahive.yml up -d >/dev/null 2>&1 )
  ( cd "$DH_REPO" && nohup .venv/bin/datahive serve \
      --config "$DH_STATE/datahive.yaml" --state-dir "$DH_STATE" \
      > "$DH_STATE/server.log" 2>&1 & echo $! > "$DH_STATE/server.pid" )
  echo "datahive starting (pid $(cat "$DH_STATE/server.pid"))"
}

# --reload, watching src/: the frontend hot-reloads on every edit and the backend
# did not, so a change to a route could sit unloaded for hours while vite served
# a UI that already expected it. That is how the slide titles vanished — the UI
# had moved to the composited preview path while a backend from five hours
# earlier was still stripping the title from it. The same shape as the pending
# migration that morning: a live process serving happily, disagreeing with the
# source someone was reading.
start_backend() {
  # A HEALTHY backend is not necessarily the CURRENT one. If the running process
  # is older than the newest file under src/, it predates an edit and must go —
  # `up` used to print "backend already up" and return, which is exactly how a
  # stale process survives a restart you thought you performed.
  if up "http://127.0.0.1:$API_PORT/health"; then
    local pid started newest
    pid=$(ss -ltnp 2>/dev/null | awk -F'pid=' '/127.0.0.1:'"$API_PORT"' /{split($2,a,","); print a[1]; exit}')
    if [ -n "${pid:-}" ] && [ -d "/proc/$pid" ]; then
      started=$(stat -c %Y "/proc/$pid" 2>/dev/null || echo 0)
      newest=$(find "$ROOT/src" -name '*.py' -newermt "@$started" -print -quit 2>/dev/null)
      if [ -z "$newest" ]; then echo "backend already up (current)"; return; fi
      echo "backend is older than src/ — restarting it"
      kill "$pid" 2>/dev/null; sleep 3
    else
      echo "backend already up"; return
    fi
  fi
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
  # The first person to sign in on an EMPTY hive whose verified email is
  # listed here becomes an admin (spec 3.1). Inert once the hive has
  # users, so it is safe to leave set — it matters on a fresh store.
  ( cd "$ROOT" && NSIGHT_DEMO=1 \
      NSIGHT_BOOTSTRAP_ADMINS=johan@egoiq.com \
      NSIGHT_DATAHIVE_URL="http://127.0.0.1:$DH_PORT" \
      NSIGHT_DATAHIVE_TOKEN="$token" \
      NSIGHT_HOST=127.0.0.1 NSIGHT_PORT=$API_PORT PYTHONPATH=src \
      nohup .venv/bin/python -m uvicorn reportbuilder.api.server:app \
      --host 127.0.0.1 --port $API_PORT --reload --reload-dir src \
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
  restart)
    # Stop whatever holds the port, not whatever the pid file remembers: a stale
    # pid file meant `kill` hit nothing and the old process kept serving.
    pid=$(ss -ltnp 2>/dev/null | awk -F'pid=' '/127.0.0.1:'"$API_PORT"' /{split($2,a,","); print a[1]; exit}')
    [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null && echo "stopped backend pid $pid"
    sleep 3; start_backend; sleep 5; status ;;
  *) echo "usage: $0 {status|up|down|restart}"; exit 1 ;;
esac
