"""Print a session cookie for a local user, so a browser driver can sign in.

The dev stack authenticates through OIDC, which a headless driver cannot
complete. Rather than add a test-only bypass to the backend — a door that would
then exist in production too — this mints a real session through the backend's
own auth module, exactly as a successful sign-in does.

Usage (with the same datahive settings the dev backend runs with):

    TOKEN=$(python3 -c "import json;d=json.load(open('work/datahive_creds.json'));print(d.get('bearer_admin') or d['bearer'])")
    NSIGHT_DATAHIVE_URL=http://127.0.0.1:7910 NSIGHT_DATAHIVE_TOKEN="$TOKEN" PYTHONPATH=src \
      .venv/bin/python scripts/e2e/mint_session.py you@example.com > work/e2e-cookie.txt
"""
import sys

from reportbuilder.api.deps_store import build_repository, service_auth
from reportbuilder.auth import session as S
from reportbuilder.auth.keys import get_or_create_signing_key

if len(sys.argv) != 2:
    sys.exit(__doc__)

auth = service_auth()
repo = build_repository()
wanted = sys.argv[1].lower()
target = next((u for u in repo.list_users(auth) if u.email.lower() == wanted), None)
if target is None:
    sys.exit(f"no user {sys.argv[1]} in this hive")

print(S.cookie_value(get_or_create_signing_key(repo, auth),
                     S.create(repo, auth, target.id)))
