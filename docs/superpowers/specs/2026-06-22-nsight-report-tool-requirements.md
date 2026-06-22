# nSight report tool — requirements traceability catalog

_Date: 2026-06-22 · Status: draft for review · Source: `Mitä työkalun pitäisi tehdä.docx`_

Every discrete statement in the source document is extracted as one numbered requirement so
each can be addressed by test cases. Columns: **ID** · **Requirement** (faithful to the
docx) · **Scope** (IN this phase / OUT = "EI TÄRKEÄ" or deferred) · **Design §** (section in
`2026-06-22-nsight-report-tool-design.md`) · **Test approach**.

Test-approach legend: **GOLD** = golden test vs known truth · **UNIT** = unit test on
fixtures · **RENDER** = OOXML/render validation · **CONV** = PPT→PDF conversion fidelity ·
**INTEG** = datahive integration test · **UI** = UI/manual acceptance · **NFR** =
non-functional, reviewed not auto-tested.

---

## A. Core functionality (Ydintoiminnallisuus)

| ID | Requirement | Scope | Design § | Test approach |
|---|---|---|---|---|
| REQ-C-01 | Ingest standard SPSS `.sav` data in observation-matrix form (rows = cases, cols = variables). | IN | §6 | INTEG: ingest Attendo `.sav`, assert case/variable counts. |
| REQ-C-02 | Ingest captures definitions: variable names, variable labels (description texts), variable values, value labels. | IN | §6 | INTEG/UNIT: Question Model exposes all four for each variable. |
| REQ-C-03 | A dataset (numeric values + definitions) can be named, saved, and deleted. | IN | §4 | INTEG: create/rename/delete material doc; assert datahive state. |
| REQ-C-04 | Multiple datasets can be imported. | IN | §4 | INTEG: attach ≥2 materials to one case; both retrievable. |
| REQ-C-05 | The system organizes the data per question (per variable) in a sensible/meaningful way on a separate view. | IN | §6, §11 | UNIT: Question Model lists one entry per question. UI: question browser; "sensible organization" = review acceptance. |
| REQ-C-06 | Per question, define whether answered via several options (multi) or only one (single). | IN | §6 | UNIT: single/multi flag settable + persisted per question. |
| REQ-C-07 | From a single dataset, multiple PPT reports can be created. | IN | §4, §8 | INTEG: ≥2 reports under one material. |
| REQ-C-08 | A report can be named, saved, edited later, and deleted. | IN | §4, §8 | INTEG: CRUD on report definition; `reference_id` versioned replace. |
| REQ-C-09 | A report can be duplicated and saved under a different name. | IN | §8 | UNIT: duplicate yields an independent definition with new name/id. |
| REQ-C-10 | A report can include an arbitrary (free) number of variables selected from the data. | IN | §8 | UNIT: ChartSpec list of any length; render N charts. |
| REQ-C-11 | In a report, each reported variable is assigned exactly one chart type. | IN | §8, §9 | UNIT: one chart_type per ChartSpec (enforced). |
| REQ-C-12 | The same variable can use different chart types in different reports. | IN | §8 | UNIT: two reports, same variable, different chart_type, both valid. |
| REQ-C-13 | Produce **at least** these chart types: line, pie, vertical bar, stacked vertical bar, horizontal bar, stacked horizontal bar, radar, doughnut, scatterplot, funnel, combination (combination = "corresponds to PPT's combination chart"; least important). | IN | §9a | RENDER per type. Native: 9 as own chart + funnel as native stacked-bar approximation; combo image-only. Image mode: all 11. (Vertical bar=`COLUMN`, horizontal bar=`BAR`.) |
| REQ-C-14 | A reported variable can have a classifying variable; depict it stratified by the classifier's values together with all responses (Total). | IN | §7 | GOLD: cross-tab per segment + Total vs known truth. |
| REQ-C-15 | Charts use mainly percentages, but also counts and means. | IN | §7 | GOLD/UNIT: pct, count, mean each computed correctly. |
| REQ-C-16 | Chart calculations account for missing-data handling. | IN | §7 | GOLD/UNIT: base excludes missing. (Same behavior as REQ-MV-01, tested once; C-16 is the core-functionality statement, MV-01 the data-section detail.) |
| REQ-C-17 | Reports can use various ready PPT templates for presenting charts. | IN | §9 | RENDER: render same report against ≥2 templates. |
| REQ-C-18 | The resulting report matches the definitions — everything required and nothing extra. | IN | §9 | RENDER: generated deck shape == definition (chart count, no extra slides/shapes). |
| REQ-C-19a | A report can be previewed on screen. | IN | §10 | UI/CONV: preview renders the generated artifact. |
| REQ-C-19b | The user can choose the preview pagination view: PPT-style (slide-per-page) or PDF-style (continuous pages). | IN | §10 | UI: both view modes selectable, both over the same PDF artifact. |
| REQ-C-20 | Preview matches the end product in essentials: chart type, chart proportions, colors, numeric values. | IN | §10 | CONV: preview derived from the same artifact (PPT→PDF) ⇒ type/proportion/color equal by construction; **numeric values** asserted by the `pdftotext` fidelity gate (§10 layer 2). Native-edit-path color/proportion fidelity is the R3 divergence risk, separately flagged. |
| REQ-C-21 | The system produces a PDF from a report, matching the preview in essentials. | IN | §10 | CONV: PDF == preview source. |
| REQ-C-22 | The system produces a PPT from a report, matching the preview in essentials. | IN | §10 | CONV/RENDER: PPT is the preview source. |
| REQ-C-23a | In the produced PPT (native mode), charts are editable with PPT's own/equivalent tools. | IN | §9a | RENDER: native `c:chart` + embedded workbook; zero picture-shapes in chart slots. |
| REQ-C-23b | The editability covers **all** key chart properties (type, data, colors, labels, legend, axes). | IN | §9a | RENDER: assert each key property is a live OOXML chart attribute (not flattened), editable post-generation. |
| REQ-C-24 | Charts include, placed per instructions, the nine elements listed in REQ-C-24a..i below. | IN | §9 | RENDER: element profile asserts each sub-element (see a–i). |
| ⮑ REQ-C-24a | Image/chart title. | IN | §9 | RENDER: title present == ChartSpec title. |
| ⮑ REQ-C-24b | Chart-type elements (the independent parts, e.g. bars/slices). | IN | §9 | RENDER: series/points count == categories. |
| ⮑ REQ-C-24c | Axis values. | IN | §9 | RENDER: value-axis tick labels present (where applicable to type). |
| ⮑ REQ-C-24d | Axis names. | IN | §9 | RENDER: axis titles present when defined. |
| ⮑ REQ-C-24e | Category names. | IN | §9 | RENDER: category labels == value labels (REQ-D-05). |
| ⮑ REQ-C-24f | Category numeric values (data labels). | IN | §9 | RENDER: data labels present == SeriesResult values. |
| ⮑ REQ-C-24g | Legend (selitysteksti). | IN | §9 | RENDER: legend present when ≥2 series. |
| ⮑ REQ-C-24h | Sample size N. | IN | §9 | RENDER: N annotation present == SeriesResult base N. |
| ⮑ REQ-C-24i | Used filter (classifying) variable. | IN | §9 | RENDER: filter-variable annotation present when classifying var set. |
| REQ-C-25 | The same font + point size is used across charts for the same **element class** (title / axis labels / data labels / legend / category names). | IN | §9 | RENDER: per element class, font+size == the single style-spec value; assert equality across all charts in a report. |
| REQ-C-26 | Chart elements can be ordered by sorting in the tool UI (see REQ-S for the full set of sort bases). | IN | §7, §11 | UNIT: sort applied to SeriesResult order. UI: sort control. |
| REQ-C-27a | Chart-property layout is produced deterministically from **a** style spec (placement, fonts, colors, sizes). | IN | §9 | RENDER: same input ⇒ identical layout; layout values == the loaded style spec. |
| REQ-C-27b | The layout matches the **client's** separate styling PPT. | BLOCKED (R4) | §9, §14 | RENDER vs the client spec — blocked until the reference PPT is provided; Attendo deck used as interim proxy. |
| REQ-C-28a | The produced PDF opens and is a valid PDF with the expected page count. | IN | §10 | CONV: LibreOffice exit 0; `pdfinfo` parses; pages == slide count. |
| REQ-C-28b | The PDF is presentation-quality. | IN | §10 | NFR: visual review (subjective). |
| REQ-C-29a | The produced PPT opens without error / repair. | IN | §9, §10 | RENDER: OOXML schema validation + python-pptx re-open without exception (no PowerPoint-in-CI needed). |
| REQ-C-29b | The PPT is presentation-quality and editable. | IN | §9a | RENDER (editability, REQ-C-23) + NFR (visual quality). |
| REQ-C-30 | Functionality is extensible; the implementation technology enables identified additional needs. | IN | §2, §3, §9 | NFR: architecture review — `ChartRenderer` strategy (§9), adapter registry, REST seam. |

## B. UI features (Piirre)

| ID | Requirement | Scope | Design § | Test approach |
|---|---|---|---|---|
| REQ-U-01 | The UI can perform the core functionalities. | IN (thin) | §11 | UI acceptance — umbrella exercising REQ-C-03..09, C-19, C-26 via the UI. |
| REQ-U-02 | The UI is controllable by mouse and keyboard. | IN (thin) | §11 | UI acceptance. |
| REQ-U-03 | The UI is consistent across functionalities. | IN (thin) | §11 | UI review against a UI-pattern checklist. |
| REQ-U-04 | Functions split into two main areas: data and reports. | IN | §11 | UI: Case detail has Data + Reports areas. |
| REQ-U-05 | Question line items can be browsed, sorted, edited, and deleted easily. | IN | §6, §11 | UI: browse/sort/edit/delete in question browser. |
| REQ-U-06 | In the report area, reports can be previewed and duplicated. | IN | §10, §11 | UI: preview + duplicate actions. |
| REQ-U-07 | Report-window management is clear and simple. | DEFER† | §11 | UI acceptance. |
| REQ-U-08 | Report windows have size-control properties. | DEFER† | §11 | UI acceptance. |
| REQ-U-09 | Report windows have a close icon. | DEFER† | §11 | UI acceptance. |
| REQ-U-10 | Consistent terminology across the UI. | IN (thin) | §11 | Objective: glossary/terminology lint over UI strings (one term per concept). |
| REQ-U-11 | The UI feels easy and intuitive. | DEFER† | §11 | UI acceptance / usability. |
| REQ-U-12 | The UI is extensible for future wishes. | IN | §3 | NFR review. |

† **DEFER is a project phasing decision, not a source priority.** The source lists
REQ-U-07/08/09/11 in the normal "Piirre" feature list with the same weight as REQ-U-01..06;
they are deferred to the UI phase by our choice, not marked unimportant by the docx.

## C. Other functionality — EI TÄRKEÄ (explicitly not important / out of scope this phase)

| ID | Requirement | Scope | Design § | Test approach |
|---|---|---|---|---|
| REQ-X-01 | User management, implemented simply. | OUT | — | n/a this phase. |
| REQ-X-02 | Delete users. | OUT | — | n/a this phase. |
| REQ-X-03 | Create new users. | OUT | — | n/a this phase. |
| REQ-X-04 | Change passwords. | OUT | — | n/a this phase. |
| REQ-X-05 | PPT report-template management features in the UI. | OUT | — | n/a (templates consumed, not managed in UI). |
| REQ-X-06 | Importing history (prior-wave data). | OUT | — | n/a this phase (relates to the prototype's trend / wave-history dependency; not design-spec risk R4). |

## D. Data structure (Datan rakenne)

| ID | Requirement | Scope | Design § | Test approach |
|---|---|---|---|---|
| REQ-D-01 | Data is an observation matrix: rows = respondents, cols = variables = questions; cells hold each respondent's answer values. | IN | §6 | UNIT: matrix shape preserved through ingest. |
| REQ-D-02 | Values may be numeric or string; the described **need focuses on numeric** values; differing numeric types are handled uniformly. | IN (numeric focus) | §2, §6 | UNIT: mixed numeric types tabulate identically. (String variables are not addressed this phase — a phasing choice, not a source-stated exclusion.) |
| REQ-D-03 | Variable names are defined; report creation is based on variable names. | IN | §6, §8 | UNIT: ChartSpec references variables by name. |
| REQ-D-04 | Variable labels provide the question text shown on the slide. | IN | §6, §9 | RENDER: slide question text == variable label. |
| REQ-D-05 | Value labels define the explanation texts shown in the report. | IN | §6, §9 | RENDER: category names == value labels. |
| REQ-D-06 | A per-question missing-values definition determines which values are treated as missing (e.g. 99 = "En tiedä"). | IN | §6, §7 | UNIT: per-variable missing set honored in base. |
| REQ-D-07 | Other SPSS definitions are not critical for this. | SCOPE NOTE | §6 | — (non-testable scope note, not a behavior). |

## E. Single vs Multi questions

| ID | Requirement | Scope | Design § | Test approach |
|---|---|---|---|---|
| REQ-M-01 | Single questions: one option chosen, stored in one variable. | IN | §6 | UNIT: single share over one variable. |
| REQ-M-02 | Multi questions: several options (tickbox), usually stored as 0/1 across several variables; the set forming one reporting unit must be defined explicitly. | IN | §6 | UNIT: multi-group definition; auto-suggest + manual override. |
| REQ-M-03 | Multi percentage base = all respondents who answered the set (not the count of selections). | IN | §7 | GOLD: multi base == respondents-answering, not selection count. |
| REQ-M-04 | Multi questions can be reported as percentages or as counts. | IN | §7 | UNIT: both statistics over a multi group. |

## F. Missing-data handling (Puuttuvien tietojen käsittely)

| ID | Requirement | Scope | Design § | Test approach |
|---|---|---|---|---|
| REQ-MV-01 | Chart creation must account for missing data, affecting above all the percentage base. | IN | §7 | GOLD/UNIT: base reflects missing exclusion. |
| REQ-MV-02 | Two kinds of missing: Sysmis (empty cell) and user-defined Missing values. | IN | §6, §7 | UNIT: both kinds excluded from base. |

## G. Presentation of numeric values (Lukuarvojen esitys)

| ID | Requirement | Scope | Design § | Test approach |
|---|---|---|---|---|
| REQ-N-01 | Numeric values usually shown as whole percentages; format may vary (e.g. one decimal). | IN | §7, §8 | UNIT: configurable percentage decimals. |
| REQ-N-02 | Means shown in varying number formats (varying decimal counts). | IN | §7, §8 | UNIT: configurable mean decimals. |
| REQ-N-03 | Counts shown as whole numbers; rounding upward may be applied. | IN | §7, §8 | UNIT: integer counts; configurable round-up. |

## H. Sorting (Sorttaus)

| ID | Requirement | Scope | Design § | Test approach |
|---|---|---|---|---|
| REQ-S-01 | Chart elements can be sorted by: percentage magnitude, mean magnitude, count, or data presentation order. | IN | §7 | UNIT: each sort basis. |
| REQ-S-02 | The sort percentage is usually an extreme option (e.g. 1 or 5) or a sum of options (e.g. 4+5 on a 5-point scale; 5+6+7 on a 7-point scale). | IN | §7 | UNIT: top-box-sum sort with configurable codes. |
| REQ-S-03 | The **default** sort basis is percentage magnitude (the most common case; count-based sorting is supported but rarely used). | IN | §7 | UNIT: default sort == percentage magnitude. |

---

## Coverage summary

**Source-level requirements: 67** (one per discrete docx statement — Core 30 · UI 12 ·
Other/out 6 · Data 7 · Single/Multi 4 · Missing 2 · Number presentation 3 · Sorting 3).

Scope split (sums to 67):

- **IN this phase: 56.**
- **DEFER to UI phase: 4** — REQ-U-07/08/09/11 (a phasing choice; the source lists them as
  normal "Piirre" features, see the † note).
- **OUT (EI TÄRKEÄ): 6** — REQ-X-01..06 (REQ-X-06 = history import is one of these six, not a
  seventh item).
- **SCOPE NOTE (non-testable): 1** — REQ-D-07.

**Test-level expansion:** for traceable test coverage, six bundled requirements are split into
lettered sub-IDs — C-19→a/b, C-23→a/b, C-24→a..i (nine chart elements), C-27→a/b, C-28→a/b,
C-29→a/b — yielding **~83 test-level items**. Every IN/DEFER item maps to a design section and
a test approach above.

## Open dependencies affecting coverage

- **REQ-C-27b / R4:** the formal "separate PPT document" defining chart-property layout.
  REQ-C-27a (deterministic layout from *a* spec) is testable now; REQ-C-27b (match the
  *client's* spec) is **BLOCKED** until that PPT is provided — the Attendo deck in `work/` is
  the interim proxy.
- **REQ-D-02:** string-valued variables are not addressed this phase (numeric focus per source).
- **REQ-X-06 (history import):** OUT this phase; relates to the prototype's trend / wave-history
  dependency (distinct from design-spec risk R4) — note for a later phase.
- **REQ-C-08 ↔ D3:** versioned report-replace depends on new datahive wiring
  (`reference_id`/`reveal_source` on attached docs) — see design §4/§13.
