"""Two or three people building presentations at the same time.

nSight is a multi-user product: several analysts share a case, and nothing
stops two of them opening the same report. The server has two mechanisms for
that — an editing LOCK (taken on open, renewed every 30s, expiring ~2min after
an editor goes quiet) and OPTIMISTIC VERSIONING on save (the editor sends the
version it loaded; a mismatch is refused rather than merged). This exercises
both under genuine concurrency, plus the shared-resource paths where two
people's work meets: the preview cache, the render slot and the AI gate.

What each check is really asking:

  create      can two people make reports at once without colliding
  lock        does the second editor get a clear refusal naming the first
  lost update is a stale save refused, or does it silently destroy work
  guarded     can a bystander delete/rename a report someone else has open
  previews    do two people rendering at once get their OWN pictures
  titles      does the AI path stay correct when shared

Run against the local stack:

    .venv/bin/python scripts/e2e/multi_user.py --case case-xxx --material mat-xxx
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "http://localhost:8200"
SEED: dict = {}


class Person:
    """One signed-in human with their own session and their own browser tab."""

    def __init__(self, name: str, cookie_path: str):
        self.name = name
        self.cookie = open(cookie_path).read().strip()
        self.tab = f"tab-{name}"
        self.last_etag: str | None = None

    def call(self, method: str, path: str, body=None, timeout=180,
             if_match: str | None = None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Cookie": f"nsight_session={self.cookie}",
                   "Content-Type": "application/json"}
        if if_match is not None:
            headers["If-Match"] = if_match
        req = urllib.request.Request(API + path, data=data, method=method,
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                self.last_etag = r.headers.get("ETag")
                # preview-chart answers with a PNG, not JSON.
                ctype = (r.headers.get("Content-Type") or "")
                if raw and not ctype.startswith("application/json"):
                    return r.status, raw
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except Exception:  # noqa: BLE001
                return e.code, {"detail": raw[:200].decode(errors="replace")}


def _ok(label: str, passed: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if passed else 'FAIL'}] {label}"
          + (f"\n         {detail}" if detail else ""))
    return passed


# --------------------------------------------------------------- the checks ---
def check_concurrent_create(people, case: str) -> bool:
    """Everyone makes a report at the same instant."""
    start = threading.Barrier(len(people))

    def one(p: Person):
        start.wait()
        doc = dict(SEED)
        doc["name"] = f"MU {p.name} {int(time.time()*1000)%100000}"
        return p, p.call("POST", f"/cases/{case}/reports", doc)

    with ThreadPoolExecutor(max_workers=len(people)) as pool:
        results = list(pool.map(one, people))

    ids, bad = [], []
    for p, (status, body) in results:
        rid = body.get("report_id") or body.get("id")
        if status not in (200, 201) or not rid:
            bad.append(f"{p.name}: HTTP {status} {str(body)[:120]}")
        else:
            ids.append(rid)
    if bad:
        return _ok("concurrent create", False, "; ".join(bad))
    return _ok("concurrent create", len(set(ids)) == len(ids),
               f"ids={ids}" if len(set(ids)) != len(ids)
               else f"{len(ids)} distinct reports")


def check_lock_excludes(a: Person, b: Person, case: str, report: str) -> bool:
    """A takes the lock; B must be refused, and told who has it."""
    a.call("DELETE", f"/cases/{case}/reports/{report}/lock?tab={a.tab}")
    sa, _ = a.call("POST", f"/cases/{case}/reports/{report}/lock?tab={a.tab}")
    sb, bb = b.call("POST", f"/cases/{case}/reports/{report}/lock?tab={b.tab}")
    named = a.name.split()[0].lower() in str(bb.get("detail", "")).lower()
    passed = sa == 200 and sb == 409
    return _ok("lock excludes the second editor", passed and named,
               f"A={sa} B={sb} detail={bb.get('detail','')!r}"
               + ("" if named else "  <- refusal does not name the holder"))


def check_save_needs_the_lock(a: Person, b: Person, case: str, report: str) -> bool:
    """B saves a report A has open. THIS is the guard that matters.

    The editor deliberately sends no If-Match (see api.ts): version checks
    produced false conflicts — a template binding, a second tab of the same
    person, an overlapping autosave — and each one ended with somebody
    discarding unsaved work. The lock is what protects concurrent editing, so
    a save from someone who does not hold it must be refused.
    """
    a.call("POST", f"/cases/{case}/reports/{report}/lock?tab={a.tab}")
    _, doc = b.call("GET", f"/cases/{case}/reports/{report}")
    doc = dict(doc); doc["name"] = "written by the bystander"
    st, bd = b.call("PUT", f"/cases/{case}/reports/{report}", doc)
    return _ok("a save without the lock is refused", st == 409,
               f"PUT -> {st} {str(bd.get('detail',''))[:100]!r}")


def check_stale_if_match_refused(a: Person, case: str, report: str) -> bool:
    """The version mechanism itself still works, for whoever switches it on.

    api.ts says the editor would need a single in-flight save and a version
    refreshed by every write path before this is worth enabling. Until then it
    should at least not have rotted.
    """
    a.call("POST", f"/cases/{case}/reports/{report}/lock?tab={a.tab}")
    st, doc = a.call("GET", f"/cases/{case}/reports/{report}")
    etag = (a.last_etag or "").strip('"')
    if not etag:
        return _ok("stale If-Match refused", False, "no ETag on GET")
    stale = str(max(0, int(etag) - 1)) if etag.isdigit() else "0"
    st, bd = a.call("PUT", f"/cases/{case}/reports/{report}", dict(doc),
                    if_match=stale)
    return _ok("stale If-Match refused (mechanism intact)", st == 409,
               f"ETag={etag!r} sent If-Match={stale!r} -> {st} "
               f"{str(bd.get('detail',''))[:80]!r}")


def check_bystander_cannot_destroy(a: Person, b: Person, case: str,
                                   report: str) -> bool:
    """While A has it open, B must not be able to delete or rename it."""
    a.call("POST", f"/cases/{case}/reports/{report}/lock?tab={a.tab}")
    sdel, ddel = b.call("DELETE", f"/cases/{case}/reports/{report}")
    passed = sdel == 409
    return _ok("bystander cannot delete a report in use", passed,
               f"DELETE -> {sdel} {str(ddel.get('detail',''))[:90]!r}")


def check_concurrent_previews(people, material: str, charts: list) -> bool:
    """Everyone renders a DIFFERENT slide at the same moment.

    Two things at once: that nobody receives somebody else's picture (the
    preview cache is shared and keyed by material+spec, so a key that dropped
    part of the spec would serve the wrong image), and what the wait actually
    becomes when the single render slot is contended.
    """
    start = threading.Barrier(len(people))
    lat: dict[str, float] = {}
    sizes: dict[str, int] = {}
    errs = []

    def one(idx_person):
        idx, p = idx_person
        # A REAL chart spec from the report, not an invented one: the preview
        # endpoint dispatches on chart_type through the plugin registry.
        c = charts[idx % len(charts)]
        body = {k: c.get(k) for k in
                ("question_ref", "chart_type", "statistic", "classifying_var",
                 "show_not_answered", "not_answered_codes", "template_slot",
                 "sort", "elements", "number_format")}
        body["render_title"] = False      # the app never bakes the title in
        start.wait()
        t = time.monotonic()
        st, bd = p.call("POST", f"/materials/{material}/preview-chart", body)
        lat[p.name] = time.monotonic() - t
        if st != 200:
            errs.append(f"{p.name}: HTTP {st} {str(bd)[:120]}")
            return
        if not isinstance(bd, (bytes, bytearray)) or not bd.startswith(b"\x89PNG"):
            errs.append(f"{p.name}: not a PNG ({str(bd)[:80]})")
            return
        import hashlib
        sizes[p.name] = hashlib.sha256(bd).hexdigest()[:16]

    with ThreadPoolExecutor(max_workers=len(people)) as pool:
        list(pool.map(one, list(enumerate(people))))

    if errs:
        return _ok("concurrent previews", False, "; ".join(errs))
    # Different charts must not come back as the SAME image: the preview cache
    # is shared between people and keyed by material+spec, so a key that dropped
    # part of the spec would hand one person another's picture.
    distinct = len(set(sizes.values())) == len(sizes)
    waits = ", ".join(f"{n} {v:.1f}s" for n, v in sorted(lat.items()))
    return _ok("concurrent previews are each their own", distinct,
               f"waits: {waits}\n         digests: "
               + ", ".join(f"{n}={d}" for n, d in sorted(sizes.items()))
               + ("" if distinct else "\n         <- SAME image for different charts:"
                                      " the shared cache key is incomplete"))


def check_concurrent_titles(people, material: str, questions: list) -> bool:
    """The AI path under contention: everyone asks for a headline at once."""
    start = threading.Barrier(len(people))
    got, errs, lat = {}, [], {}

    def one(idx_person):
        idx, p = idx_person
        q = questions[idx % len(questions)]
        start.wait()
        t = time.monotonic()
        st, bd = p.call("POST", f"/materials/{material}/ai/slide-title",
                        {"question_ref": q, "statistic": "pct"}, timeout=180)
        lat[p.name] = time.monotonic() - t
        if st != 200:
            errs.append(f"{p.name}: HTTP {st} {str(bd.get('detail',''))[:100]}")
            return
        got[p.name] = (bd.get("title") or "").strip()

    with ThreadPoolExecutor(max_workers=len(people)) as pool:
        list(pool.map(one, list(enumerate(people))))
    if errs:
        return _ok("concurrent AI titles", False, "; ".join(errs))
    waits = ", ".join(f"{n} {v:.1f}s" for n, v in sorted(lat.items()))
    return _ok("concurrent AI titles", all(got.values()),
               f"waits: {waits}\n         " +
               "\n         ".join(f"{n}: {t[:70]!r}" for n, t in got.items()))



def check_cold_contention(people, material: str, charts: list, per_person: int,
                          run_tag: str) -> bool:
    """What the wait becomes when several people render COLD slides at once.

    Warm numbers say nothing: the backend caches a rendered slide by image
    fingerprint, so re-running the same specs measures a dictionary lookup. A
    unique `footer_note` per run is part of that fingerprint, so every slide
    here has genuinely never been drawn.

    The server renders one slide at a time on one core (render_concurrency=1),
    so this is the honest answer to "does it stay smooth with three people":
    per-person latency, and how much of it is queueing behind the others.
    """
    start = threading.Barrier(len(people))
    waits: dict[str, list[float]] = {p.name: [] for p in people}
    errs: list[str] = []

    def one(idx_person):
        idx, p = idx_person
        start.wait()
        for k in range(per_person):
            c = charts[(idx * per_person + k) % len(charts)]
            body = {key: c.get(key) for key in
                    ("question_ref", "chart_type", "statistic", "classifying_var",
                     "show_not_answered", "not_answered_codes", "template_slot",
                     "sort", "elements", "number_format")}
            body["render_title"] = False
            # never drawn before -> a real render, not a cache hit
            body["footer_note"] = f"mu {run_tag} {p.name} {k}"
            t = time.monotonic()
            st, bd = p.call("POST", f"/materials/{material}/preview-chart", body)
            waits[p.name].append(time.monotonic() - t)
            if st != 200:
                errs.append(f"{p.name}#{k}: HTTP {st} {str(bd)[:90]}")
                return

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(people)) as pool:
        list(pool.map(one, list(enumerate(people))))
    wall = time.monotonic() - t0

    if errs:
        return _ok("cold renders under contention", False, "; ".join(errs[:3]))
    allw = [w for ws in waits.values() for w in ws]
    allw.sort()
    med = statistics.median(allw)
    p90 = allw[int(len(allw) * 0.9) - 1] if len(allw) > 1 else allw[0]
    lines = "\n         ".join(
        f"{n}: median {statistics.median(ws):.1f}s worst {max(ws):.1f}s"
        for n, ws in sorted(waits.items()))
    # A slide a person is waiting on should still arrive in a few seconds.
    smooth = p90 < 10.0
    return _ok("cold renders under contention stay responsive", smooth,
               f"{len(people)}x{per_person} cold slides in {wall:.1f}s wall; "
               f"median {med:.1f}s p90 {p90:.1f}s\n         {lines}")


def check_shared_config_not_lost(people, material: str, questions: list) -> bool:
    """Everyone renames a DIFFERENT question at the same instant.

    Question labels live in the MATERIAL's config — one document shared by every
    report and every user, so two renames are a read-modify-write race on the
    same object. `_update_config` serialises them through the store's own lock;
    without it the later write puts back what it read and the other rename
    disappears with no sign of it.
    """
    start = threading.Barrier(len(people))
    mine = {p.name: (questions[i % len(questions)], f"MU-{p.name}-{int(time.time())%10000}")
            for i, p in enumerate(people)}
    errs = []

    def one(p: Person):
        qid, label = mine[p.name]
        start.wait()
        st, bd = p.call("PATCH", f"/materials/{material}/questions/{qid}/label",
                        {"label": label})
        if st != 200:
            errs.append(f"{p.name}: HTTP {st} {str(bd)[:90]}")

    with ThreadPoolExecutor(max_workers=len(people)) as pool:
        list(pool.map(one, people))
    if errs:
        return _ok("concurrent renames all survive", False, "; ".join(errs))

    st, qs = people[0].call("GET", f"/materials/{material}/questions")
    qlist = qs["questions"] if isinstance(qs, dict) else qs
    text_of = {q["qid"]: (q.get("text") or "") for q in qlist}
    lost = [f"{n}: {qid} shows {text_of.get(qid, '')[:30]!r}, wanted {label!r}"
            for n, (qid, label) in mine.items() if text_of.get(qid) != label]

    # Put the originals back so a re-run starts clean.
    for _n, (qid, _l) in mine.items():
        people[0].call("PATCH", f"/materials/{material}/questions/{qid}/label",
                       {"label": ""})
    return _ok("concurrent renames all survive (no silent loss)", not lost,
               "; ".join(lost))


def check_abandoned_lock_frees_itself(a: Person, b: Person, case: str,
                                      report: str, ttl: int) -> bool:
    """A closes the laptop. B must eventually be able to work.

    A browser that crashes, a laptop that closes and a network that drops all
    fail to run any release, so a lock that only cleared on request would strand
    the report and there would be nothing a colleague could do about it. A
    stops renewing here; nothing else happens.
    """
    a.call("POST", f"/cases/{case}/reports/{report}/lock?tab={a.tab}")
    st_before, _ = b.call("POST", f"/cases/{case}/reports/{report}/lock?tab={b.tab}")
    if st_before != 409:
        return _ok("an abandoned lock frees itself", False,
                   f"B was not blocked to begin with (HTTP {st_before})")
    wait = ttl + 10
    print(f"         (A stops renewing; waiting {wait}s for the lock to lapse)",
          flush=True)
    time.sleep(wait)
    st_after, bd = b.call("POST", f"/cases/{case}/reports/{report}/lock?tab={b.tab}")
    b.call("DELETE", f"/cases/{case}/reports/{report}/lock?tab={b.tab}")
    return _ok("an abandoned lock frees itself", st_after == 200,
               f"blocked at first (409), after {wait}s -> {st_after} "
               f"{str(bd.get('detail',''))[:70]!r}")


def _fresh_report(p: Person, case: str, name: str) -> str:
    st, made = p.call("POST", f"/cases/{case}/reports", dict(SEED, name=name))
    return made.get("report_id") or ""


def check_same_report_render_is_single_flight(a: Person, b: Person, case: str,
                                              material: str, report: str) -> bool:
    """Two people press Generate on the SAME report. One must be refused.

    Otherwise two LibreOffice pipelines write the same deterministic output
    directory at once, and whoever downloads gets a deck assembled from both.
    """
    def go(who):
        return who.call("POST", f"/cases/{case}/reports/{report}/render",
                        {"material_id": material}, timeout=600)

    start = threading.Barrier(2)
    out = {}

    def one(item):
        tag, who = item
        start.wait()
        out[tag] = go(who)[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(one, [("a", a), ("b", b)]))
    codes = sorted(out.values())
    passed = codes.count(409) == 1 and any(c == 200 for c in codes)
    return _ok("same report: a second Generate is refused", passed,
               f"codes={out}")


def check_previews_during_a_deck_build(a: Person, b: Person, case: str,
                                       material: str, charts: list,
                                       run_tag: str) -> bool:
    """A builds a whole deck; B keeps editing. Does B's work still arrive?

    This is the collision that matters: a deck build is minutes of LibreOffice
    on the same single core that draws B's previews. B should stay usable, not
    be frozen out until the deck finishes.
    """
    report = _fresh_report(a, case, f"MU deck {run_tag}")
    if not report:
        return _ok("previews stay responsive during a deck build", False,
                   "could not create a report to render")

    # Baseline first: one cold preview for B with nothing else running.
    def cold(idx: int) -> tuple[int, float]:
        c = charts[idx % len(charts)]
        body = {k: c.get(k) for k in
                ("question_ref", "chart_type", "statistic", "classifying_var",
                 "show_not_answered", "not_answered_codes", "template_slot",
                 "sort", "elements", "number_format")}
        body["render_title"] = False
        body["footer_note"] = f"deck {run_tag} {idx}"
        t = time.monotonic()
        st, _ = b.call("POST", f"/materials/{material}/preview-chart", body,
                       timeout=300)
        return st, time.monotonic() - t

    st0, base = cold(0)
    if st0 != 200:
        return _ok("previews stay responsive during a deck build", False,
                   f"baseline preview failed: HTTP {st0}")

    deck: dict = {}

    def build():
        t = time.monotonic()
        st, bd = a.call("POST", f"/cases/{case}/reports/{report}/render",
                        {"material_id": material}, timeout=1800)
        deck["status"], deck["secs"] = st, time.monotonic() - t

    t_start = time.monotonic()
    thread = threading.Thread(target=build, daemon=True)
    thread.start()
    time.sleep(3)                      # let the deck build get going

    during: list[float] = []
    fails = []
    idx = 1
    while thread.is_alive() and time.monotonic() - t_start < 900:
        st, secs = cold(idx)
        idx += 1
        if st != 200:
            fails.append(f"HTTP {st}")
            break
        during.append(secs)
        if len(during) >= 5:
            break
    thread.join(timeout=900)

    if fails:
        return _ok("previews stay responsive during a deck build", False,
                   f"B's preview failed while the deck built: {fails[0]}")
    if not during:
        return _ok("previews stay responsive during a deck build", True,
                   f"deck finished in {deck.get('secs', 0):.0f}s before a "
                   f"preview could be timed")
    worst = max(during)
    med = statistics.median(during)
    # Contended, but a person must not be locked out. 5x the quiet time is
    # already unpleasant; beyond that the editor is unusable during a build.
    passed = deck.get("status") == 200 and worst < max(15.0, base * 8)
    return _ok("previews stay responsive during a deck build", passed,
               f"deck {deck.get('status')} in {deck.get('secs',0):.0f}s; "
               f"B quiet {base:.1f}s -> during median {med:.1f}s worst {worst:.1f}s "
               f"({med/base:.1f}x)")


def check_two_decks_at_once(a: Person, b: Person, case: str, material: str,
                            run_tag: str) -> bool:
    """Two people generate DIFFERENT decks at the same time.

    Nothing caps this: the single-flight guard is per report, so both pipelines
    run, each starting LibreOffice on the same core.
    """
    ra = _fresh_report(a, case, f"MU deckA {run_tag}")
    rb = _fresh_report(b, case, f"MU deckB {run_tag}")
    if not (ra and rb):
        return _ok("two decks at once both complete", False, "setup failed")
    start = threading.Barrier(2)
    res = {}

    def one(item):
        tag, who, rid = item
        start.wait()
        t = time.monotonic()
        st, bd = who.call("POST", f"/cases/{case}/reports/{rid}/render",
                          {"material_id": material}, timeout=1800)
        res[tag] = (st, time.monotonic() - t, str(bd)[:80])

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(one, [("A", a, ra), ("B", b, rb)]))
    passed = all(v[0] == 200 for v in res.values())
    return _ok("two decks at once both complete", passed,
               "; ".join(f"{k}: HTTP {v[0]} in {v[1]:.0f}s {v[2] if v[0]!=200 else ''}"
                         for k, v in sorted(res.items())))


OPS = ["read", "save", "preview", "title", "rename", "list", "questions"]


def check_mixed_workload(people, case: str, material: str, charts: list,
                         questions: list, seconds: int, run_tag: str) -> bool:
    """Everybody works on THEIR OWN report, doing everything, all at once.

    This is the real shape of the product: several analysts each building a
    different presentation in the same case at the same time. Each person here
    holds their own report's lock and then loops over the whole set of
    operations — reading, saving, rendering cold previews, asking for AI
    headlines, renaming questions in the SHARED material config, listing the
    case — with the mix shuffled per person so the interleavings differ.

    The bar is that NOTHING BREAKS: no 5xx, and no 4xx that is not a documented
    refusal. Latency is reported but is not the assertion.
    """
    import random

    reports = {}
    for p in people:
        rid = _fresh_report(p, case, f"MU stress {p.name} {run_tag}")
        if not rid:
            return _ok("mixed workload", False, f"{p.name}: no report")
        reports[p.name] = rid
        p.call("POST", f"/cases/{case}/reports/{rid}/lock?tab={p.tab}")

    stop = time.monotonic() + seconds
    bad: list[str] = []
    counts: dict[str, int] = {}
    lat: dict[str, list[float]] = {}
    start = threading.Barrier(len(people))

    def record(op: str, st: int, secs: float, body, allowed=(200, 201)):
        counts[op] = counts.get(op, 0) + 1
        lat.setdefault(op, []).append(secs)
        if st not in allowed:
            bad.append(f"{op} -> HTTP {st} {str(body)[:90]}")

    def worker(person_idx):
        idx, p = person_idx
        rid = reports[p.name]
        rng = random.Random(1000 + idx)
        n = 0
        start.wait()
        while time.monotonic() < stop and not bad:
            n += 1
            op = rng.choice(OPS)
            t = time.monotonic()
            if op == "read":
                st, bd = p.call("GET", f"/cases/{case}/reports/{rid}")
            elif op == "save":
                st, doc = p.call("GET", f"/cases/{case}/reports/{rid}")
                doc = dict(doc); doc["name"] = f"MU stress {p.name} {run_tag} #{n}"
                st, bd = p.call("PUT", f"/cases/{case}/reports/{rid}", doc)
            elif op == "preview":
                c = charts[rng.randrange(len(charts))]
                body = {k: c.get(k) for k in
                        ("question_ref", "chart_type", "statistic",
                         "classifying_var", "show_not_answered",
                         "not_answered_codes", "template_slot", "sort",
                         "elements", "number_format")}
                body["render_title"] = False
                body["footer_note"] = f"stress {run_tag} {p.name} {n}"
                st, bd = p.call("POST", f"/materials/{material}/preview-chart",
                                body, timeout=300)
            elif op == "title":
                q = questions[rng.randrange(len(questions))]
                st, bd = p.call("POST", f"/materials/{material}/ai/slide-title",
                                {"question_ref": q, "statistic": "pct"},
                                timeout=300)
            elif op == "rename":
                q = questions[rng.randrange(len(questions))]
                st, bd = p.call("PATCH",
                                f"/materials/{material}/questions/{q}/label",
                                {"label": f"{p.name}-{n}"})
            elif op == "list":
                st, bd = p.call("GET", f"/cases/{case}/reports")
            else:
                st, bd = p.call("GET", f"/materials/{material}/questions")
            record(op, st, time.monotonic() - t, bd if st >= 400 else None)

    with ThreadPoolExecutor(max_workers=len(people)) as pool:
        list(pool.map(worker, list(enumerate(people))))

    # Tidy: release locks, clear the labels this churned, drop the reports.
    for p in people:
        rid = reports[p.name]
        p.call("DELETE", f"/cases/{case}/reports/{rid}/lock?tab={p.tab}")
        p.call("DELETE", f"/cases/{case}/reports/{rid}")
    for q in questions:
        people[0].call("PATCH", f"/materials/{material}/questions/{q}/label",
                       {"label": ""})

    total = sum(counts.values())
    summary = "  ".join(
        f"{op}={counts[op]}({statistics.median(lat[op]):.1f}s)"
        for op in sorted(counts))
    return _ok(f"mixed workload: {len(people)} people, {total} operations",
               not bad,
               (f"{summary}" if not bad else
                f"{len(bad)} failure(s):\n         " + "\n         ".join(bad[:5])))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--material", required=True)
    ap.add_argument("--cookies", default="work/mu",
                    help="directory of <name>.cookie files, one per person")
    ap.add_argument("--people", default="alice,bob,johan")
    ap.add_argument("--ops", default="",
                    help="restrict the mixed workload to these operations, "
                         "e.g. read,save,list — isolates I/O from CPU work")
    ap.add_argument("--stress", type=int, default=0, metavar="SECONDS",
                    help="everyone hammers their OWN report with a mixed "
                         "workload for this many seconds")
    ap.add_argument("--decks", action="store_true",
                    help="also build whole decks (minutes of LibreOffice)")
    ap.add_argument("--slow", action="store_true",
                    help="also wait out the lock TTL to prove a stranded report frees")
    ap.add_argument("--ttl", type=int, default=120, help="lock TTL seconds")
    ap.add_argument("--slides", type=int, default=4,
                    help="cold slides each person renders in the contention check")
    a = ap.parse_args()

    if a.ops:
        global OPS
        OPS = [o.strip() for o in a.ops.split(",") if o.strip()]
    people = [Person(n, f"{a.cookies}/{n}.cookie") for n in a.people.split(",")]
    print(f"{len(people)} people: {', '.join(p.name for p in people)}\n")

    # A report they can all fight over, and questions to render. Creating one
    # needs a whole report doc, so seed from an existing report in the case —
    # which is what "Copy as new" does.
    global SEED
    _, existing = people[0].call("GET", f"/cases/{a.case}/reports")
    seed_id = (existing.get("reports") or [{}])[0].get("report_id")
    if not seed_id:
        print("no existing report in this case to seed from")
        return 1
    _, SEED = people[0].call("GET", f"/cases/{a.case}/reports/{seed_id}")
    st, made = people[0].call("POST", f"/cases/{a.case}/reports",
                              dict(SEED, name=f"MU shared {int(time.time())}"))
    shared = made.get("report_id") or made.get("id")
    if not shared:
        print(f"could not create the shared report: HTTP {st} {made}")
        return 1
    st, qs = people[0].call("GET", f"/materials/{a.material}/questions")
    qlist = qs["questions"] if isinstance(qs, dict) else qs
    refs = [q["qid"] for q in qlist][:8]
    print(f"shared report {shared}; {len(refs)} questions available\n")

    results = []
    print("CORRECTNESS")
    results.append(check_concurrent_create(people, a.case))
    if len(people) >= 2:
        # Everything below needs a second person to be refused by the first.
        results.append(check_lock_excludes(people[0], people[1], a.case, shared))
        results.append(check_save_needs_the_lock(people[0], people[1], a.case, shared))
        results.append(check_stale_if_match_refused(people[0], a.case, shared))
        results.append(check_bystander_cannot_destroy(people[0], people[1],
                                                     a.case, shared))
    else:
        print("  (one person: the pairwise refusal checks need two)")
    if a.slow and len(people) >= 2:
        results.append(check_abandoned_lock_frees_itself(
            people[0], people[1], a.case, shared, a.ttl))
    print("\nSHARED RESOURCES")
    charts = (SEED.get("charts") or [])[:8]
    results.append(check_concurrent_previews(people, a.material, charts))
    results.append(check_concurrent_titles(people, a.material, refs))
    results.append(check_shared_config_not_lost(people, a.material, refs))
    results.append(check_cold_contention(people, a.material, charts,
                                         a.slides, str(int(time.time()))))
    if a.stress:
        print("\nMIXED WORKLOAD (everyone on their OWN report)")
        results.append(check_mixed_workload(
            people, a.case, a.material, charts, refs, a.stress,
            str(int(time.time()))))
    if a.decks and len(people) >= 2:
        print("\nDECK GENERATION")
        tag = str(int(time.time()))
        results.append(check_same_report_render_is_single_flight(
            people[0], people[1], a.case, a.material, shared))
        results.append(check_previews_during_a_deck_build(
            people[0], people[1], a.case, a.material, charts, tag))
        results.append(check_two_decks_at_once(
            people[0], people[1], a.case, a.material, tag))

    # Tidy: release the lock so a re-run is not blocked by this one.
    people[0].call("DELETE", f"/cases/{a.case}/reports/{shared}/lock?tab={people[0].tab}")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
