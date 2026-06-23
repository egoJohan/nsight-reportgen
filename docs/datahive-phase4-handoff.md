# datahive changes for nSight (Phase 4 / D1–D3) — handoff

**Audience:** a session working in the **egoiq/egohive-datahive** repo.
**Purpose:** make datahive the system of record for nSight's Case / Material / Report model and
serve it over REST, without compromising datahive's genericity. Everything below is generic
container/dataset/document/aggregation work — **none of it is nSight-specific**.

---

## 0. The one standing constraint — genericity guardrail (G1)

> datahive's genericity and architectural simplicity must not be endangered by nSight-specific
> needs. **Every new change must read as generic** — containers / datasets / documents /
> aggregation. No `nSight`, `survey`, `chart`, `report-the-product`, `percentage`, or `statistic`
> in any code, path, payload key, template name, or test. nSight semantics live ONLY in the nSight
> backend and inside **opaque document payloads datahive never parses**.

Review every diff against G1. (Note: datahive already ships an SPSS/SAV connector and a
`survey_codebook` MCP tool that predate the guardrail — those existing surfaces are grandfathered;
the guardrail governs **new** changes.)

A second standing rule already in datahive: **shared-service-layer** — each app has one service
module that owns logic + auth/ABAC/audit; REST and MCP are **thin adapters** over it. Add new
behavior to the service layer first, then expose it through both adapters.

---

## 1. What nSight needs, in one sentence

nSight stores **Cases** (= datahive *projects*), each holding **Materials** (uploaded SPSS `.sav`
datasets) and **Reports** (opaque report-definition JSON), and calls datahive over **REST** for
all of it; the same data is reachable by agents over **MCP** for discussion. Mapping:

| nSight concept | datahive generic construct |
|---|---|
| Case | a **project** (existing projects app) |
| Material (an uploaded `.sav`) | a dataset/document attached to the project (raw bytes + the existing SAV/tabular ingest) |
| Report (definition JSON) | an **opaque raw document** attached to the project, versioned by a stable `reference_id` |
| List / navigate cases | existing generic surfaces: `list_projects`, `project_status`, `recall`, `inventory` |
| Cross-tab / counts | a new **generic aggregation primitive** (GROUP BY counts), reusable by any consumer |

---

## 2. The exact contract datahive's REST API must satisfy

This is the integration surface. The nSight backend has a `DataHiveClient` with **8 methods**; each
must map to a generic datahive REST endpoint. Get these signatures and round-trip semantics right
and the integration is done:

| nSight client method | Needs from datahive (generic) | Round-trip guarantee |
|---|---|---|
| `create_case(name) -> id` | create a project from a generic template | returns project id |
| `list_cases() -> [{id,name}]` | list admitted projects | ABAC-filtered |
| `attach_material(case_id, name, sav_bytes, codebook_summary) -> id` | attach a dataset/raw doc (binary `.sav`) under a project | returns material/doc id |
| `get_material(material_id) -> bytes` | return the **exact stored `.sav` bytes** | **byte-exact** |
| `save_report(case_id, report_id\|None, report_json, readable) -> id` | attach an **opaque** raw doc; `report_id=None` creates, a given id **versioned-replaces** | returns doc id |
| `load_report(report_doc_id) -> str` | return the **exact** stored report JSON string | **byte-exact** |
| `delete_report(report_doc_id) -> None` | delete a raw doc | — |
| `aggregate(material_id, group_by, filters, weight=None) -> {dimensions,cells,total}` | generic filtered GROUP BY counts over a tabular dataset | counts == in-process recompute |

The two **byte-exact** rows are the most important acceptance criteria (a report definition must
survive store→load unchanged, char-for-char).

---

## 3. The three capabilities (D1 / D2 / D3) and the grounded changes

These are written against datahive's current source (verified while planning). File paths/symbols
are datahive's; confirm they still hold.

### D3 — opaque raw-document round-trip (the load-bearing one for Reports)
**Why:** today `attach_doc` (`datahive/projects/service.py:~247`) calls
`remember(text=…, classify=True)` **without** a `reference_id` — so it's classified/indexed and not
a verbatim, addressable, replaceable record. Reports need lossless, versioned, opaque storage.
**Do:**
1. **Service layer** — add `attach_raw_doc(*, hive, store, tenant_id, actor, project_id, label,
   name, reference_id, text) -> dict` and `read_raw_doc(*, hive, store, tenant_id, reference_id)
   -> str`. `attach_raw_doc` → `remember(..., classify=False, reference_id=...)` (opaque,
   versioned-replace on same id); `read_raw_doc` resolves via
   `store.find_resource_record_by_reference_id(..., workspace_uuid=projects_workspace(tenant_id))`
   then `hive.reveal_source`. Unit tests: byte-exact round-trip; re-attach same id replaces.
2. **MCP adapter** — add `attach_project_raw_doc` / `read_project_raw_doc` to
   `datahive/api/routers/mcp_server.py` (mirror `_call_attach_project_doc`: write guard + consent +
   `_viewer_identity`), register in the dispatch dict + generic tool schemas. Integration test:
   attach exact JSON under `reference_id`, read identical, re-attach replaces.

### D2 — projects REST router + shared-service-layer parity
**Why:** the projects app has **MCP tools but no REST router**; the nSight backend calls datahive
over REST.
**Do:** create `datahive/api/routers/projects.py` under `/api/v1/projects`, ABAC mirroring the MCP
path, register in `app.py`:
- `GET ""` → `{count, projects:[{id,name}]}` (delegates to `_ps.list_projects`) — backs `list_cases`.
- `GET /{project_id}` → status (delegates to `_ps.project_status`); 404 unless admitted.
- `POST ""` → create project from a template — backs `create_case`.
- `POST /{id}/docs` → `attach_raw_doc` (lossless), returns `{reference_id}` — backs
  `attach_material` / `save_report`.
- `POST /{id}/advance` → workflow advance.
- **Add a delete** for a raw doc (e.g. `DELETE /{id}/docs/{reference_id}`) — backs `delete_report`.
  *(This one is NOT in the original Phase-4 plan: `delete_report` was added to the nSight client
  after that plan was written. Include it.)*
Reuse the MCP write guard (`_entity_write_guard` → 403) + consent gate; map `ProjectError` → 400.
Pydantic bodies use **generic** keys (`name` / `template_ref` / `label` / `reference_id` /
`to_phase`). If `_effective_read_scope` / `_viewer_identity` are private to `mcp_server`, lift them
to a shared `api/_authscope.py`. Unit tests (mock Request, like `tests/api/test_references_rest.py`).

### D1 — generic aggregation primitive (GROUP BY counts)
**Why:** `TabularStore.query` (`datahive/storage/tabular.py:~253`) is `SELECT * … WHERE … LIMIT` —
**no GROUP BY**. nSight needs cross-tab cell counts. **Not on the hard critical path** — the nSight
engine can fetch rows and aggregate in-process until this lands — but it's the clean, scalable path.
**Do:**
1. **Service** — add `TabularStore.group_by_counts(*, item_id, group_columns, filters=None,
   scope_groups=None, scope_ceiling=None) -> {"dimensions","cells":[{"key","count"}],"total"}`,
   reusing `_user_columns` / `_build_user_filter` / ABAC clauses from `query`; validate group
   columns (`unknown_column:` else); parameterised SQL with `_safe_ident`. Add
   `datahive/aggregation/service.py::aggregate(...)` thin wrapper (dict filters → `FilterClause`,
   `asyncio.to_thread`).
2. **REST** — `datahive/api/routers/aggregation.py`: `POST /api/v1/aggregation/{item_id}` body
   `{group_columns, filters}` → `{dimensions,cells,total}`; ABAC scope from the bearer
   (`auth.scope.groups`, `regulatory_ceiling`); `TabularFilterError` → 400; register in `app.py`.
Guardrail: only `group_by_counts` / `cells` / `dimensions` — **no** statistic / percentage / survey
concept. Backs `DataHiveClient.aggregate`.

### Supporting — generic workflow template (D2)
Define `template_ref="wftemplate:dataset-report-study"` (generic — **NOT** "survey") as pure data
via the existing `create_workflow_template`: phases `ingested → reported (required_docs:[{label:
"report"}]) → delivered (is_terminal)`. No new datahive code — `_validate_template_spec` already
accepts it. `create_case` creates a project from this template; advancing to `reported` is gated
until a `report` raw-doc is attached.

---

## 4. Two things to resolve early (not fully settled by the original plan)

1. **Binary materials.** `attach_material`/`get_material` move the raw **`.sav` bytes** (binary).
   The D3 raw-doc round-trip (4.1) is **text**-oriented (`remember(text=…)` / `reveal_source`).
   Decide: base64-encode the `.sav` into the raw-doc text, OR add a binary-capable raw-doc path, OR
   lean on datahive's **existing SPSS/SAV connector** to ingest the dataset (for the D1 tabular
   side) while still storing the raw bytes for nSight's in-process `read_sav`. nSight's
   `get_material` requires the **exact bytes back**, so whatever path is chosen must be byte-exact.
2. **Delete.** `delete_report` (REQ-C-12) needs a raw-doc delete endpoint — add it (see D2 above).

---

## 5. Testing & acceptance

- datahive-side: `@pytest.mark.unit` mock-Request tests (like `tests/api/test_references_rest.py`)
  + `@pytest.mark.integration` MCP/REST tests (like `tests/integration/test_projects.py`); run
  `make test-unit` / `make test-integration`.
- **Acceptance gate (cross-repo):** the nSight repo already has a skipped integration test
  (`tests/rb/api/test_integration_hive.py`, and a fuller `tests/rb/e2e/test_api_e2e.py` that today
  runs against an in-memory fake). When datahive is ready, implement nSight's `DataHiveClient`
  methods as thin REST calls and point them at a running test hive via `NSIGHT_TEST_HIVE_URL`
  (+token). The acceptance criteria: `create_case`+`list`; **report JSON byte-exact on load**;
  versioned replace; `aggregate` counts == in-process recompute. That proves D1/D2/D3 together
  (REQ-C-03/04/07/08/12).

---

## 6. What the nSight side already provides (so datahive scope is clear)

- The full client contract is committed at `src/reportbuilder/store/datahive_client.py` (8 methods,
  currently `NotImplementedError` stubs) — **this file is the spec** for the REST surface.
- nSight's REST API (FastAPI) already calls these 8 methods; routes are tested against a mock and an
  in-memory fake. When the real REST client lands, nothing in the nSight routers changes.
- Report definitions are **opaque JSON** to datahive — nSight serializes/deserializes them
  (`report_to_json` / `report_from_json`); datahive only stores and returns the exact string.
