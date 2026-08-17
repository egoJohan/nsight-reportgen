# Production spec (Speksi 2) — requirements analysis

_Date: 2026-08-12 · Source: `Mitä työkalun pitäisi tehdä - Speksi 2 Tuotantoversio.docx`
(modified 2026-08-11) · Supersedes: `2026-06-22-nsight-report-tool-requirements.md`
(from `Mitä työkalun pitäisi tehdä.docx`)_

The client states the framing explicitly: *"Tämä dokumentti ei ole kehitysroadmap vaan
tässä kuvataan ainoastaan se mitä tehdään tuotantoversioon."* — everything listed is in
scope for the production version. There is no "EI TÄRKEÄ" section any more.

Status legend against the current build: **BUILT** · **PARTIAL** · **MISSING** ·
**OPEN** (the client's own unanswered question).

---

## 1. What actually changed from Speksi 1

This is the part that drives the plan. Seven changes matter.

### 1.1 Charts become images — native editability is dropped

> "Järjestelmän tuottamassa ppt:ssä kuvaajat esitetään templatelle vietävinä kuvina.
> **Kuvaajien ei tarvitse olla editoitavia ppt:ssä.**"

Speksi 1 (REQ-C-23a/b) required live OOXML charts editable with PowerPoint's own tools,
covering *all* key chart properties. That requirement is gone, replaced by its opposite.

This is the single largest scope reduction in the document, and it retires a whole class
of known defects: findings 10 and 14 in `2026-08-06-separate-panels-followups.md` are both
native-vs-image divergences (`BAR_STACKED` vs `BAR_STACKED_100`, and transposed stacking).
Under Speksi 2 the fix is to **retire native mode**, not to reconcile it.

**Decision needed:** delete `render/native/` and the `render_mode` field, or keep native
as a dormant option. Recommend deleting — a second renderer that no requirement asks for
is a permanent correctness tax, and it is already provably out of sync with the one that
ships.

### 1.2 PDF output is dropped

Speksi 1 had REQ-C-21 (produce a PDF) and REQ-C-19b (user chooses PPT-style or PDF-style
preview pagination). Speksi 2 mentions PDF **nowhere**. Preview must match *ppt-tiedostoa*;
output is *ppt-tiedosto*.

Note this is a spec-text change, not necessarily a product change: the current preview is
implemented *as* a PDF render (`export/pdf_convert.py`, `StepDownload` embeds the PDF in an
iframe), and the PDF download button costs nothing to keep. What goes away is the
*obligation* — PDF fidelity is no longer an acceptance criterion.

### 1.3 The customer layer is new, and user management moves from "not important" to in scope

Speksi 1: *"Muu toiminnallisuus – EI TÄRKEÄ"* — user management, template management, all
explicitly deprioritised (catalogued as REQ-X-01..06, OUT).

Speksi 2 gives that section a full page of detail and no disclaimer:

- **Three-level structure: Asiakas – Case – Raportti.** The build has two levels (Case –
  Report). Every store key, route, and UI breadcrumb is `case_id`-rooted.
- User accounts, passwords, permissions, user groups, admin role.
- Permissions inherit from customer → case, with a per-case exception ("käyttäjällä voi
  olla pääsy pelkästään yksittäiseen caseen, ei koko asiakkuuteen").

There is **no authentication of any kind** in the current codebase. This is the largest
net-new build in the document.

### 1.4 The three-phase model is now normative

Speksi 1: *"Toiminnot jakautuvat kahteen pääalueeseen: dataan ja raportteihin"* plus a set
of floating report windows (REQ-U-07/08/09 — size controls, close icons).

Speksi 2: Select → Design → Preview, defined twice (once in core functionality, once in
UI). The report-window requirements are **gone entirely**.

The build already ships this (`ReportWizard.tsx` steps are labelled Select / Design /
Preview). The prototype's shape was validated.

### 1.5 One variable, many slides

> "Kukin muuttuja voidaan ottaa yhden raportin sisällä useammalle sivulle ja siitä voidaan
> luoda eri sivuille eri kuvaajia"

Speksi 1 said one chart type per variable per report (REQ-C-11). Speksi 2 lifts that to
per-slide, and adds that different slides for the same variable may use *different
classifying variables*. The build anticipated this: `ChartSpec.slide_id` exists precisely
because `question_ref` stopped being unique when the compare-groups section landed.

### 1.6 Two classifying variables in one chart

> "Yhteen kuvaajaan voidaan liittää rinnakkain kaksi erilaista luokittelevaa muuttujaa"

Built (`classifying_var_2`, and the separate-classifier-panels work of 2026-08-04).

### 1.7 Named new controls that were implicit before

Percent direction on multi-variable charts, editable chart text in Design, editable N
notation, sorting by a *sum* of answer options, a chart **subtitle** (alaotsikko) added to
the element list, and limited multi-chart pages (three pies per slide).

---

## 2. Requirement catalog

### A. Core functionality (Ydintoiminnallisuudet)

| ID | Requirement | Δ vs Speksi 1 | Status |
|---|---|---|---|
| P-C-01 | Ingest standard SPSS `.sav` (observation matrix + variable names, variable labels, values, value labels). Dataset can be named, saved, deleted. | same | PARTIAL — ingest + naming built; **no delete-material endpoint** (`routes_materials.py` has GET/POST only) |
| P-C-02 | Multiple datasets (cases) can be imported. | same | BUILT |
| P-C-03 | A case is processed in three phases: **Select** (choose variables) → **Design** (per-question chart type + settings) → **Preview** (inspect content and layout, save to a chosen PPT template). | **NEW** | BUILT |
| P-C-04 | Data is organised per question (per variable) on a separate view. | same | BUILT |
| P-C-05 | Per question, define single vs multi. | same | BUILT |
| P-C-06 | Multiple reports per dataset; name, save, edit later, delete, duplicate under a new name. | same | BUILT |
| P-C-07 | Free number of variables per report. | same | BUILT |
| P-C-08 | One chart type per variable per report; the same variable may use different types in different reports. | same | BUILT |
| P-C-09 | At least 11 chart types: line, pie, vertical bar, stacked vertical bar, horizontal bar, stacked horizontal bar, radar, doughnut, scatterplot, funnel, combination (least important). | same | BUILT (`ChartType`, all 11 + wordcloud) |
| P-C-10 | The same variable can be placed on **several pages** within one report, with a different chart on each. | **NEW** | PARTIAL — model supports it (`slide_id`); Select-step UI is question-keyed, needs an explicit "add another slide for this question" affordance |
| P-C-11 | A reported variable can be given a classifying variable; it is shown stratified by that classifier's values together with Total. | same | BUILT |
| P-C-12 | **HUOM!** How and where a classifying variable appears in the classifying-variable menu is still to be specified. | **NEW — client's own open item** | OPEN |
| P-C-13 | Two different classifying variables can be attached side by side to one chart (e.g. gender × age). | **NEW** | BUILT (`classifying_var_2`) |
| P-C-14 | When one variable is reported on several pages, those pages may use different classifying variables in parallel. | **NEW** | PARTIAL — follows from P-C-10 |
| P-C-15 | Charts show mainly percentages, but also counts and means. | same | BUILT |
| P-C-16 | On multi-variable charts the user can influence **which direction percentages are computed from**. | **NEW (named)** | BUILT (`percent_base`: auto/classifier/question/total) — but see follow-up 7: the control is still offered where the engine overrides it |
| P-C-17 | Missing-data handling is applied in chart calculation. | same | BUILT |
| P-C-18 | Missing data = absent from the data entirely (Sysmis) **or** an SPSS-defined missing value. | same | BUILT |
| P-C-19 | Reports can use ready-made PPT templates; the same report can be directed at different templates. | strengthened ("sama raportti eri pohjille") | PARTIAL — `Report.template_ref` exists; no template library, no per-report re-target flow |
| P-C-20 | The generated report matches the definitions — everything required, nothing extra. | same | BUILT (`assert_complete`) |
| P-C-21 | On-screen preview paginated like the PPT, matching it in chart type, proportions, colours and numeric values. | narrowed (PDF-pagination option dropped) | BUILT |
| P-C-22 | The system produces a PPT matching the preview in essentials. | same | BUILT |
| P-C-23 | In the PPT, charts are **images** placed on the template. **They need not be editable.** | **CHANGED — reverses Speksi 1 REQ-C-23** | BUILT (image mode) — action is to *remove* native mode |
| P-C-24 | Charts carry, placed per the styling instructions: title · **subtitle** · chart-type elements · axis values · axis names · category names · category numeric values · legend · N · the classifying variable used · consistent font+size per element class. | subtitle is **NEW**; rest same | BUILT (subtitle = `slide_description`) |
| P-C-25 | Chart elements can be sorted in the UI, by percentage magnitude or by the data's own order. | same | BUILT |
| P-C-26 | Elements can be sorted by a **sum of percentages** — e.g. by 5+6+7 or 4+5. | promoted from the Sorting appendix to a core requirement | BUILT (`SortSpec.topbox_sum`) |
| P-C-27 | Chart **text properties** (title, subtitle, value names, axis names) are editable in the Design view. | **NEW** | PARTIAL — title, subtitle and category labels are editable; **axis names are a boolean toggle only** (`ElementToggles.axis_names`), with no editable text anywhere |
| P-C-28 | The **N presentation** is editable. | **NEW** | BUILT (`footer_note`, `{n}` / `{stat}` placeholders) |
| P-C-29 | Several charts on one page, **limited**: three pies per page. May partly be solved by generating separate slides and moving them in PPT. *"Tämän ominaisuuden lopullinen määrittely tarkentuu tuotantovaiheessa."* | **NEW — and explicitly unfinished by the client** | MISSING (nearest precedent: `demographics_grid`) · OPEN |
| P-C-30 | Chart property layout follows the separate PPT styling document. | same | PARTIAL — was BLOCKED/R4 in Speksi 1; still depends on that document being supplied |
| P-C-31 | The resulting PPT is usable. | same (PDF twin dropped) | BUILT |
| P-C-32 | Functionality is extensible in directions specified later. | same | NFR |

### B. User interface (Käyttöliittymä)

| ID | Requirement | Δ | Status |
|---|---|---|---|
| P-U-01 | The UI performs the core functions in a jointly agreed, **sufficiently easy** way. | wording strengthened | NFR |
| P-U-02 | Mouse and keyboard control. | same | PARTIAL — keyboard coverage unverified |
| P-U-03 | Consistent across functionalities. | same | NFR |
| P-U-04 | Three main views: Select, Design, Preview. | **CHANGED** from two areas (data / reports) | BUILT |
| P-U-05 | Questions and their charts can be browsed, sorted, edited and deleted easily. **Design presents all of the report's charts in one long, easily navigable list.** | second sentence **NEW** | BUILT (`StepConfigure` list + drag reorder) |
| P-U-06 | Definitions made in each view can be **saved as an intermediate save**. | **NEW** | PARTIAL — autosave exists; no explicit user-visible Save |
| P-U-07 | Moving between views is simple. | **NEW** | BUILT (stepper) |
| P-U-08 | Consistent terminology throughout. | same | NFR |
| P-U-09 | The UI feels easy and intuitive. | same | NFR |
| P-U-10 | The UI is extensible. | same | NFR |
| — | *Speksi 1's report-window requirements (floating windows, size controls, close icon) are **gone**.* | REMOVED | n/a |

### C. Other functionality (Muut toiminnallisuudet) — **was "EI TÄRKEÄ", now in scope**

| ID | Requirement | Δ | Status |
|---|---|---|---|
| P-O-01 | Three-level customer structure **Asiakas – Case – Raportti**: a customer has many cases, a case has many reports; every report belongs to a case, every case to a customer. | **NEW** | MISSING — the store, API and UI are two-level |
| P-O-02 | User management: manage an individual account, its password and its permissions, implemented simply. | was OUT | MISSING |
| P-O-03 | User **grouping** probably needed — e.g. "nSight users" who automatically get the same rights. | **NEW**, client-flagged as uncertain ("luultavasti") | OPEN |
| P-O-04 | Create and delete users. | was OUT | MISSING |
| P-O-05 | Permission type: access to a **customer**. | **NEW** | MISSING |
| P-O-06 | Permission type: access to a **single case**. | **NEW** | MISSING |
| P-O-07 | Permissions inherit from the customer level by default, but a user may hold access to a single case without access to the whole customer. | **NEW** | MISSING |
| P-O-08 | Admin role: may create users and assign permissions. | **NEW** | MISSING |
| P-O-09 | Who has the right to change passwords? | **OPEN — client's question** | OPEN |
| P-O-10 | Does access to a customer or case imply the right to **edit** an existing report? | **OPEN — client's question** | OPEN |
| P-O-11 | PPT template management in the UI: **add template, delete template**. | was OUT (REQ-X-05) | MISSING |
| P-O-12 | Management of past cases and their reports — to be thought through. An archive is probably **not** needed; old material is downloaded into nSight's own Teams. | **NEW**, client-flagged unresolved | OPEN — leaning "no archive feature", confirm |
| — | *Speksi 1's "Historian tuominen" (wave-history import) is **gone**.* | REMOVED | n/a |

### D–H. Appendices — unchanged from Speksi 1

Data structure (7), single vs multi (4), missing-data handling (2), presentation of numeric
values (3), sorting (3) are **word-for-word identical** to Speksi 1. The Speksi 1 catalog
entries REQ-D-01..07, REQ-M-01..04, REQ-MV-01/02, REQ-N-01..03, REQ-S-01..03 carry over
verbatim, along with their test approaches. All are BUILT.

The only movement is that sorting-by-sum (REQ-S-02) was promoted into the main body as
P-C-26 — the client wanted it visible, not buried in an appendix.

**Total: 69 source requirements** (Core 32 · UI 10 · Other 12 · appendices 15 shared with
Speksi 1). Zero are marked out of scope by the source.

---

## 3. Gaps, sized

**Large — net-new subsystems, nothing to build on:**

1. **Identity and authorisation** (P-O-02, 04, 05, 06, 07, 08). No auth exists anywhere in
   `src/reportbuilder`. Needs: user store, login, session/token, an authorisation check on
   every route, and an admin UI. Every existing endpoint is currently open.
2. **The customer layer** (P-O-01). Touches `store/`, all five routers, and the UI's
   navigation root. Best done *before* auth, since permissions are defined in terms of it.

**Medium:**

3. **Template management** (P-O-11 + P-C-19). Upload/delete templates, bind a report to
   one, re-render the same report against another. `Report.template_ref` is the hook.
4. **Multi-chart pages** (P-C-29). Blocked on the client's own definition; `demographics_grid`
   shows the layout mechanism already exists.
5. **Retiring native render mode** (P-C-23). A deletion, but it reaches `deck.py`,
   `render/native/`, `model/report.py`, the completeness/purity guards and their tests.

**Small:**

6. Axis-name text editing (P-C-27) — the one text property with a toggle but no editor.
7. Explicit "add another slide for this question" in Select (P-C-10, P-C-14).
8. Material delete endpoint (P-C-01).
9. A visible Save control per view (P-U-06).

**Carried, unresolved from Speksi 1:**

10. The styling PPT (P-C-30) is still not in hand. It was R4/BLOCKED in June and the
    production spec repeats the requirement unchanged. This is the one dependency that can
    silently invalidate finished rendering work.

**Known defects that intersect these requirements** (from
`2026-08-06-separate-panels-followups.md`, all still open): thin-segment label collisions
(1), battery×classifier label collisions (2), the phantom small-multiples panel (3), 17
charts computing to zero categories (9), the 2 genuinely non-partition slides (audit), and
4 orphan reports (13). Findings 10 and 14 dissolve when native mode goes.

---

## 4. Questions the client left open

These are in the document itself, not inferred. They need answers before the affected work
can be planned.

1. **P-C-12** — how and where does a variable become available in the classifying-variable
   menu? (Currently every variable is offered; the client wants a rule.)
2. **P-C-29** — final definition of multi-chart pages. Is "three pies per slide" the whole
   requirement, or the first instance of a general grid?
3. **P-O-03** — are user groups needed, or is per-user permission enough for v1?
4. **P-O-09** — who may change passwords: the user, an admin, or both?
5. **P-O-10** — does read access to a customer/case grant edit rights on its reports, or is
   editing a separate permission?
6. **P-O-12** — confirm that no archive feature is needed (old cases exported to Teams).

Two more the document does not raise but which its own changes force:

7. Should native chart mode be **deleted** or retained as a dormant option? (P-C-23)
8. Should the PDF download survive as a convenience now that PDF is not a requirement?
   (§1.2)

---

## 5. Suggested sequencing

1. Answer the six open questions above — several block design, none block code.
2. **Customer layer** (P-O-01) — schema-level, cheapest before auth exists.
3. **Auth + permissions** (P-O-02..08) — defined in terms of customer/case.
4. **Retire native mode** (P-C-23) — removes two known defects and halves render surface.
5. **Template management** (P-O-11, P-C-19).
6. Small gaps 6–9 — each is a day or less.
7. **Multi-chart pages** (P-C-29) once defined.
8. Chase the styling PPT (P-C-30) in parallel throughout.
