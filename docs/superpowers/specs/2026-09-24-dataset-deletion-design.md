# Deleting a study's dataset makes the study read-only

Requirement P-C-01 (spec 2): *"Datasetti (numeeriset arvot + määritykset)
voidaan nimetä, tallentaa ja poistaa."* Design agreed with Johan, 2026-09-24.

## What exists today, and why it changes

Deleting a dataset already exists (`bbad593`, 2026-08-20, live on staging):
`DELETE /cases/{case_id}/materials/{material_id}`, `Repository.delete_material`,
and a "Delete this dataset?" dialog in `web/src/components/DataTab.tsx`. It
deletes the SPSS file, its curation and the stored decks, and **keeps** the
report definitions, which then chart nothing.

The agreed behaviour is the reverse, and the current one has gaps:

- decks built from the deleted data stay downloadable — the report meta still
  says `rendered`, and `preview.pdf`/`preview.pptx` serve the server's local
  deck cache without any check;
- only the deleting user's workspace forgets the dataset; other users keep a
  stale `materialId`;
- nothing stops a delete while someone edits or renders a report, and a render
  already running saves its deck back after the delete;
- the deleted dataset's accepted sensitive terms stay on the tenant's masking
  list until someone next accepts terms.

## The rule

When a study's **last** dataset is deleted, the study becomes **read-only for
good**, for every user — exactly what a user with *Read only* access sees today:

- the reports that have a generated deck stay listed, each with PDF and PPTX
  downloads and nothing else: no opening, editing, duplicating or generating;
- report definitions are deleted; reports with no generated deck are deleted
  entirely;
- a new dataset cannot be imported into it. New work on new data is a new study.

Deleting one of several datasets in a study (left behind by "Replace file")
while others remain removes only that file; the study stays editable on the
remaining one.

## 1. State

`case.json` gains:

```json
"dataset_deleted": {"at": "2026-09-24T18:02:11+00:00", "by": "usr-…",
                    "by_name": "Johan Wessberg", "files": ["Q3-2026.sav"],
                    "completed": true}
```

Absent means the study is live. `completed` is `false` from the moment the
study is marked until the last step of the delete has run (§3); `files` names
what was deleted, for the banner. It is the single source of truth: every screen
and every user reads it from the server, so no per-user setting can get it
wrong. `Case` (the repository's case record) exposes it as `dataset_deleted:
dict | None`; `GET /cases/{id}` and the case list return it.

## 2. Read-only is enforced on the server

The check lives **inside the write guards themselves** (`require_case_write`,
`require_case_in_customer_write`, `require_material_write` in
`api/deps_auth.py`, via `refuse_if_read_only`): every route that writes to a
study already passes through one of them, so none can be forgotten. It refuses
with **409**
`{"error": "study_read_only", "detail": "This study is read-only: its dataset
was deleted on <date>."}` when `dataset_deleted` is set. Every route that writes
to a study, or starts work that would, takes it instead of or in addition to
`require_case_write`:

- reports: create, update (save), duplicate, delete a single report, lock/beat;
- render: `POST …/render`, and the deck persist step (checked again at save
  time, so a render already running when the delete starts saves nothing);
- materials: upload, delete, config writes (question labels, value merges,
  dropped words, marked classifiers, sensitive terms);
- grouping/regroup, AI routes that write, report template pin;
- the study itself: renaming it, or changing its template.

A test walks the app's own routes and requires every write (POST, PUT, PATCH,
DELETE) addressed by a study id to be refused, so a route added later is
covered too. It found one legitimate exception, kept: `PUT
/settings/workspace/{case_id}` — a user's OWN screen state, stored in their
settings, which writes nothing to the study.

**Exceptions:**

- `DELETE /cases/{case_id}` — deleting the whole study — stays allowed, so an
  archive can be removed completely.
- While `completed` is `false`, `DELETE /cases/{case_id}/materials/{mid}` stays
  allowed, so an interrupted delete can always be finished (§3). Nothing else
  does.

Someone who took a lock between the delete's lock check and the marking loses
nothing already saved; their next save is refused with the read-only message.
That is accepted: the check makes it a race of seconds, and the alternative —
holding a study-wide lock across a delete that may wait for consent — would
block everyone for as long as the consent takes.

Reads stay allowed: the case, the report list, deck downloads.

## 3. Deleting the dataset

`Repository.delete_material` (and the route) changes. Order, each step safe to
repeat, so datahive's `consent_required` retries and an interrupted delete both
converge:

1. **Refuse** with 409 if anyone other than the caller holds a live lock on a
   report in the study — the same rule as deleting a study. Skipped when
   resuming (`completed` is `false`): the study is already read-only.
2. If this is **not** the study's last dataset: delete `material/{mid}` and
   `material/{mid}.config`, clear that material's caches (step 6), done.
3. **Mark the study** `dataset_deleted` with `completed: false` (write
   `case.json`) — first, so from here on nothing new is written.
4. **For each report:** if `report/{rid}.pptx` exists **in the store**, delete
   `report/{rid}` (the definition) and rewrite `report/{rid}.meta` to the
   deck-only form: `{id, name, has_render: true, rendered_at, deck_only: true}`
   — no `render_key`, no template pin. Otherwise delete `report/{rid}`,
   `.meta`, `.pptx` and `.lock` entirely.
   *What counts as a deck:* the stored `.pptx`, whatever its age. A report
   edited after its deck was generated keeps that deck — it is what was
   delivered — shown with the date it was generated. A deck that exists only in
   one server's local cache (its save to the store failed) does not count: the
   store is the record, and the warning (§5) uses exactly this rule, so what it
   says will be kept is what is kept.
5. **Delete the datasets:** every `material/{mid}` and `.config` in the case.
6. **Clear derived data:** the material's preview images
   (`preview_root`, the per-material marker), the local deck cache
   `render_root/{case}/*` (decks are served from the store from now on), the
   parsed-file cache entry, the location cache.
7. **Mark the delete finished:** `completed: true`.
8. After it, best-effort: **clear derived data** (step 6 of the list above,
   done by the route) and **re-register the tenant's masking terms** without
   the deleted dataset's accepted terms. A failure here only leaves those terms
   masked — more masking, never less — until the next acceptance anywhere
   re-registers the union.

**Interrupted?** Datahive may stop any delete to ask a human for consent
(`consent_required`, returned as 409 with an approve link), and a process can
die mid-way. Every step checks what is already done and moves on, so calling
the same `DELETE` again converges. While `completed` is `false` the study page
shows *"Deleting the dataset did not finish"* with a **Finish deleting** button
that makes that call; the study is read-only meanwhile, so nothing is written
in between.

`GET …/materials/{mid}/usage` returns, for the warning:
`{"last_dataset": bool, "remaining": [file names…], "with_deck": [names…],
"without_deck": [names…]}` — `with_deck`/`without_deck` by the §3 step 4 rule.

## 4. What the read-only study shows

- **List** (`GET /cases/{id}/reports`): only deck-only reports, each with
  `deck_only: true`, `rendered: true`, `rendered_at`.
- **Downloads:** for a deck-only report, `preview.pptx` and `preview.pdf`
  check the deck-only state **before** anything else — before the local deck
  cache that serves live reports — and serve only the stored
  `report/{rid}.pptx`, with no `render_key` check (there is nothing left to
  check it against). The PDF is converted from that PPTX once and cached.
  Access is the same read grant as today.
- **Report definition:** `GET …/reports/{rid}` answers 404 for a deck-only
  report; the UI never opens the report editor in a read-only study, and
  ignores any dataset a user's workspace still remembers for it.
- **Study page:** a banner — *"Read only: the dataset <file> was deleted on
  <date> by <name>. Only the generated decks remain."* No "New report", no
  Data-tab import or curation.
- **Study list:** a "Read only" label on the study.
- **Report rows:** a "Dataset deleted" label, the date the deck was generated,
  and only the PDF and PPTX buttons.

## 4b. Backups keep the decks of read-only studies

The whole-store backup leaves decks out (`EXCLUDED_LABELS` in
`store/backup.py`) because a live report's deck can be generated again from its
definition. A read-only study's decks cannot — they are all that is left. The
backup includes the `.pptx` of every deck-only report; restore brings it back
with its label, and a test proves a read-only study round-trips through backup
and restore with its decks.

## 5. The warning

**Keep the decks?** When the study has generated decks, the warning offers a
tick box — *"Keep the N generated decks for download (PDF and PPTX)"* —
**ticked by default**. Left empty, the decks and every report go too; the
study is still read-only, now empty, and can then be deleted with **Delete
study**. ("If there is deck/PDF downloadable, let's have a tick box whether to
leave those or delete." — Johan, 2026-09-24.) The choice travels as
`?keep_decks=false` and is recorded as `keep_decks` in `dataset_deleted`, so a
resumed delete keeps to it.


Shown by the Data tab's delete button, from the usage endpoint.

When it is the study's last dataset:

> **Delete this dataset?**
> This makes the study read-only for good. Report definitions are deleted:
> reports can no longer be opened, edited, duplicated or generated again. Only
> the decks already generated remain, for download as PDF and PPTX.
>
> **3 reports have no generated deck and will be deleted entirely:**
> Report A, Report B, Report C.

The second paragraph appears only when there are such reports.

When other datasets remain, a shorter warning that names what the reports
will use from then on — reports do not record their dataset, and the study
picks the remaining one:

> **Delete this dataset?** This removes the file "<name>" and its curation. The
> study's reports will use "<remaining>" from now on.

## 6. Testing

- **Repository** (in-memory hive): the delete order; a study with decks and
  without; a stale deck kept; the not-last-dataset case; a delete interrupted
  after each step and retried converges, and only the dataset delete is allowed
  while `completed` is `false`; a lock held elsewhere refuses; the deck-only
  meta form; backup and restore of a read-only study keep its decks.
- **API**: every write route refuses 409 `study_read_only` on a read-only
  study; deleting the whole study still works; the list returns deck-only
  reports; `preview.pptx`/`preview.pdf` serve the stored deck; a render
  finishing after the delete saves nothing; the usage endpoint.
- **Frontend** (vitest): the warning's text for both cases and the
  no-deck list; the read-only banner and report label.
- **Against a real hive**: the whole flow on a disposable copy of the local hive
  (restored from the Phase 1 archive), as in `docs/local-hive-upgrade.md`.

## Existing data

Checked on staging (read-only, 2026-09-24): 24 studies, none holding reports
without a dataset (what the old delete left behind) and none with more than one
dataset. No study needs converting.

## Out of scope

- Undoing a dataset deletion. The decks remain; the definitions do not.
- Changing "Replace file" (it still adds a dataset and leaves the old one).
- Staging's existing studies: none is read-only until someone deletes a dataset.
