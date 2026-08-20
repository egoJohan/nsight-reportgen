"""Installing a font by hand — the only route for the real customer templates.

Attendo, Synsam and Holiday Club all name commercial fonts, so automatic
resolution can never supply them (see render.fonts). These cover the manual
path: what gets stored, what is refused, and what the admin is told is missing.

The host's font directory and fontconfig are stubbed. A test that really ran
fc-cache would install fonts on the developer's machine and pass or fail
depending on what was already there.
"""
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.render import fonts as F
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.integration


@pytest.fixture
def auth():
    return AuthContext(token="admin-1")


@pytest.fixture
def store_repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def client_store(store_repo, auth):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: store_repo
    app.dependency_overrides[get_auth] = lambda: auth
    return TestClient(app)

# Minimal but real-shaped: an sfnt magic number is what install_font_bytes
# checks before it will write anything.
TTF = b"\x00\x01\x00\x00" + b"\x00" * 64
OTF = b"OTTO" + b"\x00" * 64
WOFF = b"wOFF" + b"\x00" * 64


@pytest.fixture
def host(tmp_path, monkeypatch):
    """A fake render host: fonts land in tmp_path and fontconfig 'sees' them."""
    installed: set[str] = set()
    monkeypatch.setattr(F, "FONT_DIR", tmp_path / "fonts")
    monkeypatch.setattr(F, "_refresh_font_cache", lambda: None)
    monkeypatch.setattr(F, "installed_families", lambda **_: installed)
    monkeypatch.setattr(F, "is_installed_after_refresh",
                        lambda fam: fam.strip().lower() in installed)
    # Every uploaded file claims to be this family; family_of reads the real
    # name table, which our stub bytes do not have.
    monkeypatch.setattr(F, "family_of", lambda blob: "Brand Sans")

    def install(blob, *, filename="font.ttf", family=""):
        if not blob.startswith((b"\x00\x01\x00\x00", b"OTTO")):
            return F.FontStatus(family or filename, F.UNAVAILABLE,
                                reason="Tiedosto ei ole .ttf- tai .otf-fontti.")
        fam = family or "Brand Sans"
        installed.add(fam.lower())
        (F.FONT_DIR).mkdir(parents=True, exist_ok=True)
        (F.FONT_DIR / f"{fam}.ttf").write_bytes(blob)
        return F.FontStatus(fam, F.INSTALLED, source="upload")

    monkeypatch.setattr(F, "install_font_bytes", install)
    monkeypatch.setattr(F, "remove_font_file",
                        lambda fam: bool(installed.discard(fam.lower()) or True))
    return installed


def _upload(client, blob, name="brand.ttf"):
    return client.post("/settings/fonts",
                       files={"file": (name, blob, "font/sfnt")})


# --- uploading --------------------------------------------------------------

def test_uploaded_font_is_stored_and_installed(client_store, host):
    resp = _upload(client_store, TTF)

    assert resp.status_code == 201
    body = resp.json()
    assert body["family"] == "Brand Sans"
    assert body["on_host"] is True
    assert "Brand Sans".lower() in host


def test_opentype_is_accepted_too(client_store, host):
    assert _upload(client_store, OTF, "brand.otf").status_code == 201


def test_web_font_is_refused_with_a_reason(client_store, host):
    """A .woff renamed .ttf is the likely mistake and must not install quietly."""
    resp = _upload(client_store, WOFF)

    assert resp.status_code == 422
    assert "ttf" in resp.json()["detail"].lower()
    assert not host


def test_empty_upload_is_refused(client_store, host):
    assert _upload(client_store, b"").status_code == 422


# --- listing ----------------------------------------------------------------

def test_listing_reports_what_is_on_the_host(client_store, host):
    _upload(client_store, TTF)

    body = client_store.get("/settings/fonts").json()

    assert [f["family"] for f in body["fonts"]] == ["Brand Sans"]
    assert body["fonts"][0]["on_host"] is True


def test_font_stored_but_absent_from_the_host_is_flagged(client_store, host):
    """The case a startup sync is meant to fix: in datahive, not on this box."""
    _upload(client_store, TTF)
    host.clear()

    body = client_store.get("/settings/fonts").json()

    assert body["fonts"][0]["on_host"] is False


def test_missing_families_name_the_templates_that_need_them(client_store, host,
                                                            store_repo, auth):
    """The actionable half: what to upload, and for whose deck."""
    store_repo.create_customer(auth, "Attendo")
    customer = store_repo.list_customers(auth)[0]
    store_repo.upload_template(
        auth, customer.id, "Attendo.pptx", b"PK-not-a-real-deck",
        {"heading_font": "Century Gothic",
         "fonts": [{"family": "Century Gothic", "state": "unavailable",
                    "ok": False, "reason": "kaupallinen fontti"},
                   {"family": "Arial", "state": "present", "ok": True,
                    "reason": ""}]})

    missing = client_store.get("/settings/fonts").json()["missing"]

    assert [m["family"] for m in missing] == ["Century Gothic"]
    assert missing[0]["templates"] == ["Attendo.pptx"]


# --- deleting ---------------------------------------------------------------

def test_deleting_asks_for_consent_first(client_store, host):
    """datahive gates destructive operations; the caller must be able to act."""
    fid = _upload(client_store, TTF).json()["id"]

    resp = client_store.delete(f"/settings/fonts/{fid}")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "consent_required"
    assert detail["request_id"]          # what the user approves
    assert detail["approve"]             # and where
    # Nothing was removed while consent was outstanding.
    assert len(client_store.get("/settings/fonts").json()["fonts"]) == 1


def test_deleting_after_approval_removes_it_everywhere(client_store, host,
                                                       store_repo):
    """A font is two objects — the file and its metadata — and datahive gates
    each one, so a cascade takes an approval per object rather than one for the
    whole delete. The route stays retryable: approve, call again, repeat."""
    fid = _upload(client_store, TTF).json()["id"]

    for _ in range(5):
        resp = client_store.delete(f"/settings/fonts/{fid}")
        if resp.status_code != 409:
            break
        store_repo.store.approve(resp.json()["detail"]["request_id"])

    assert resp.status_code == 200
    assert resp.json()["family"] == "Brand Sans"
    assert client_store.get("/settings/fonts").json()["fonts"] == []


# --- startup sync -----------------------------------------------------------

def test_sync_puts_stored_fonts_back_on_a_fresh_host(client_store, host,
                                                     store_repo, auth):
    """A replaced host starts empty; the fonts have to come back by themselves."""
    from reportbuilder.api.routes_settings import sync_fonts_to_host

    _upload(client_store, TTF)
    host.clear()                      # new machine, empty font directory

    results = sync_fonts_to_host(store_repo, auth)

    assert [r.family for r in results] == ["Brand Sans"]
    assert "brand sans" in host


def test_sync_on_an_empty_hive_is_a_no_op(client_store, host, store_repo, auth):
    from reportbuilder.api.routes_settings import sync_fonts_to_host

    assert sync_fonts_to_host(store_repo, auth) == []


# --- chart font -------------------------------------------------------------
#
# Deliberately NOT the template's font. A brand display face is often wide and
# chart text is mostly long category labels, so the admin can pick a narrower
# one and fit more of a label before it truncates.

def test_chart_font_defaults_to_the_house_face(client_store, host):
    body = client_store.get("/settings/chart-font").json()

    assert body["family"] == ""                     # nothing chosen
    assert body["effective"] == body["default"]     # so the house face applies
    assert body["available"]                        # and there is a list to pick from


def test_setting_a_chart_font_sticks(client_store, host):
    available = client_store.get("/settings/chart-font").json()["available"]
    choice = next(f for f in available if f != "Liberation Sans")

    resp = client_store.put("/settings/chart-font", json={"family": choice})

    assert resp.status_code == 200
    assert resp.json()["effective"] == choice
    assert client_store.get("/settings/chart-font").json()["family"] == choice


def test_clearing_it_restores_the_house_face(client_store, host):
    available = client_store.get("/settings/chart-font").json()["available"]
    client_store.put("/settings/chart-font",
                     json={"family": next(f for f in available
                                          if f != "Liberation Sans")})

    client_store.put("/settings/chart-font", json={"family": ""})

    body = client_store.get("/settings/chart-font").json()
    assert body["family"] == ""
    assert body["effective"] == body["default"]


def test_a_font_this_host_lacks_is_refused(client_store, host):
    """Accepting it would leave charts silently drawn in something else."""
    resp = client_store.put("/settings/chart-font",
                            json={"family": "Definitely Not Installed"})

    assert resp.status_code == 422
    assert "is not installed" in resp.json()["detail"]
    assert client_store.get("/settings/chart-font").json()["family"] == ""


# --- substitutions ----------------------------------------------------------
#
# Render-side only. The .pptx keeps naming the real font so a client who has it
# still sees their own brand; only what we rasterise here changes.

@pytest.fixture
def subs(tmp_path, monkeypatch):
    """Point the fontconfig rule file at a temp path, not the real ~/.config."""
    monkeypatch.setattr(F, "SUBSTITUTION_FILE", tmp_path / "99-nsight.conf")
    monkeypatch.setattr(F, "_substitutions", {}, raising=False)
    return F.SUBSTITUTION_FILE


def test_substitution_writes_a_fontconfig_rule(client_store, subs):
    available = client_store.get("/settings/chart-font").json()["available"]
    stand_in = available[0]

    resp = client_store.put("/settings/font-substitutions",
                            json={"map": {"Century Gothic": stand_in}})

    assert resp.status_code == 200
    assert resp.json()["map"] == {"Century Gothic": stand_in}
    rule = subs.read_text()
    assert "Century Gothic" in rule and stand_in in rule


def test_substitution_survives_a_reread(client_store, subs):
    available = client_store.get("/settings/chart-font").json()["available"]
    client_store.put("/settings/font-substitutions",
                     json={"map": {"Century Gothic": available[0]}})

    body = client_store.get("/settings/font-substitutions").json()

    assert body["map"] == {"Century Gothic": available[0]}


def test_clearing_substitutions_removes_the_rule_file(client_store, subs):
    available = client_store.get("/settings/chart-font").json()["available"]
    client_store.put("/settings/font-substitutions",
                     json={"map": {"Century Gothic": available[0]}})

    client_store.put("/settings/font-substitutions", json={"map": {}})

    assert not subs.exists()          # host back to its own behaviour


def test_substituting_with_a_font_we_lack_is_refused(client_store, subs):
    resp = client_store.put("/settings/font-substitutions",
                            json={"map": {"Century Gothic": "Not Installed"}})

    assert resp.status_code == 422
    assert not subs.exists()


def test_a_substituted_font_no_longer_reads_as_a_problem(subs, monkeypatch):
    """The warning was about silence, not about exactness.

    Once an admin has chosen the stand-in, they have been told — so the row
    stops being an error and says what it renders as instead.
    """
    monkeypatch.setattr(F, "installed_families", lambda **_: set())
    F.apply_substitutions({"Century Gothic": "DejaVu Serif"})

    st = F.ensure_font("Century Gothic", allow_network=False)

    assert st.state == F.SUBSTITUTED
    assert st.ok                       # resolved, deliberately
    assert st.substitute == "DejaVu Serif"
    assert "The PowerPoint file still refers to" in st.reason
