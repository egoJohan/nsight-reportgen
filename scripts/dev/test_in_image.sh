#!/usr/bin/env bash
# Run the test suite INSIDE the backend image staging runs.
#
# The laptop's .venv is Python 3.13; Dockerfile.backend is 3.11, with its own
# LibreOffice, poppler and fonts. A defect can live in one and not the other:
# the DuckDB abort at interpreter exit (1aadcfb) was specific to 3.13, and the
# LibreOffice helpers left as zombies (gpgconf, gpg, gpgsm) exist only where
# the server is PID 1 in a container. Run this before a deploy that touches
# the engine, the render toolchain or the process model.
#
# The image is built exactly as deploy builds it; the dev extra (pytest) is
# added in a throwaway container, never baked into the image that ships.
#
# Usage:  scripts/dev/test_in_image.sh [pytest args...]
#         default args: -q -n 4
set -euo pipefail
cd "$(dirname "$0")/../.."

TAG=nsight-backend:test-in-image
ARGS=("$@")
[ ${#ARGS[@]} -gt 0 ] || ARGS=(-q -n 4)

echo "building $TAG from Dockerfile.backend"
docker build -q -f Dockerfile.backend -t "$TAG" . >/dev/null

# --init as on staging (docker-compose.staging.yml). Tests read-only from the
# working tree, with the other directories some tests read (never work/, which
# holds credentials); the venv's dev extra is installed into the container only.
docker run --rm --init \
  -v "$PWD/tests:/app/tests:ro" \
  -v "$PWD/pyproject.toml:/app/pyproject.toml:ro" \
  $(for d in web docs input ui acceptance deploy scripts; do
      [ -e "$d" ] && printf -- '-v %s/%s:/app/%s:ro ' "$PWD" "$d" "$d"; done) \
  -e NSIGHT_DISABLE_CLEANUP=1 \
  -e NSIGHT_CACHE_DIR=/var/cache/nsight \
  -e TMPDIR=/var/cache/nsight/scratch \
  -e MALLOC_ARENA_MAX=2 \
  --entrypoint sh "$TAG" -c '
    set -e
    mkdir -p /var/cache/nsight/scratch
    uv sync --frozen --extra dev -q
    # pytest-xdist is in pyproject.toml but not in uv.lock (added without a
    # relock), so --frozen leaves it out; fetched here for -n, never shipped.
    uv pip install -q pytest-xdist
    exec /app/.venv/bin/python -m pytest -p no:cacheprovider "$@"
  ' sh "${ARGS[@]}"
