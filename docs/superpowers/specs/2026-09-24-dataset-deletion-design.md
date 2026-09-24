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
"dataset_deleted": {"at": "2026-09-24T18:02:11+00:00", "by": "usr-…", "by_name": "Johan Wessberg"}
```

Absent means the study is live. It is the single source of truth: every screen
and every user reads it from the server, so no per-user setting can get it
wrong. `Case` (the repository's case record) exposes it as `dataset_deleted:
dict | None`; `GET /cases/{id}` and the case list return it.

## 2. Read-only is enforced on the server

A dependency `require_case_live` (in `api/deps_auth.py`, next to
`require_case_write`) resolves the case and refuses with **409**
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

The rule for completeness: **every route that takes `require_case_write`
also takes `require_case_live`**, except `DELETE /cases/{case_id}`. The
implementation lists them, and a test walks the app's routes to prove no
`require_case_write` route was missed.

**Exception:** `DELETE /cases/{case_id}` — deleting the whole study — stays
allowed, so an archive can be removed completely.

Reads stay allowed: the case, the report list, deck downloads.

## 3. Deleting the dataset

`Repository.delete_material` (and the route) changes. Order, each step safe to
repeat, so datahive's `consent_required` retries and an interrupted delete both
converge:

1. **Refuse** with 409 if anyone other than the caller holds a live lock on a
   report in the study — the same rule as deleting a study.
2. If this is **not** the study's last dataset: delete `material/{mid}` and
   `material/{mid}.config`, clear that material's caches (step 6), done.
3. **Mark the study** `dataset_deleted` (write `case.json`) — first, so from
   here on nothing new is written.
4. **For each report:** if `report/{rid}.pptx` exists, delete `report/{rid}`
   (the definition) and rewrite `report/{rid}.meta` to the deck-only form:
   `{id, name, has_render: true, rendered_at, deck_only: true}` — no
   `render_key`, no template pin. Otherwise delete `report/{rid}`, `.meta`,
   `.pptx` and `.lock` entirely.
5. **Delete the datasets:** every `material/{mid}` and `.config` in the case.
6. **Clear derived data:** the material's preview images
   (`preview_root`, the per-material marker), the local deck cache
   `render_root/{case}/*` (decks are served from the store from now on), the
   parsed-file cache entry, the location cache.
7. **Re-register the tenant's masking terms** without the deleted dataset's
   accepted terms.

`GET …/materials/{mid}/usage` returns, for the warning:
`{"last_dataset": bool, "with_deck": [names…], "without_deck": [names…]}`.

## 4. What the read-only study shows

- **List** (`GET /cases/{id}/reports`): only deck-only reports, each with
  `deck_only: true`, `rendered: true`, `rendered_at`.
- **Downloads:** for a deck-only report, `preview.pptx` returns the stored
  `report/{rid}.pptx` with no `render_key` check (there is nothing left to
  check it against); `preview.pdf` converts that PPTX once and caches the PDF
  locally.
- **Study page:** a banner — *"Read only: the dataset was deleted on <date> by
  <name>. Only the generated decks remain."* No "New report", no Data-tab import
  or curation.
- **Report rows:** a "Dataset deleted" label, and only the PDF and PPTX buttons.

## 5. The warning

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

When other datasets remain, the existing, shorter warning about removing that
file is kept.

## 6. Testing

- **Repository** (in-memory hive): the delete order; a study with decks and
  without; the not-last-dataset case; a delete interrupted after each step and
  retried converges; a lock held elsewhere refuses; the deck-only meta form.
- **API**: every write route refuses 409 `study_read_only` on a read-only
  study; deleting the whole study still works; the list returns deck-only
  reports; `preview.pptx`/`preview.pdf` serve the stored deck; a render
  finishing after the delete saves nothing; the usage endpoint.
- **Frontend** (vitest): the warning's text for both cases and the
  no-deck list; the read-only banner and report label.
- **Against a real hive**: the whole flow on a disposable copy of the local hive
  (restored from the Phase 1 archive), as in `docs/local-hive-upgrade.md`.

## Out of scope

- Undoing a dataset deletion. The decks remain; the definitions do not.
- Changing "Replace file" (it still adds a dataset and leaves the old one).
- Staging's existing studies: none is read-only until someone deletes a dataset.
