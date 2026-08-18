# Labels in datahive are inconsistent across stores

_Date: 2026-08-18 · For a datahive session · Found while specifying nSight's storage
contract (`docs/superpowers/specs/2026-08-17-datahive-api-contract.md`)_

## The problem

Datahive has three places to put something, and three different answers to "what is this?"

| Store | Label model | Filter |
|---|---|---|
| **items** (`api/routers/items.py`) | `labels: list[str]` + `pinned_labels: list[str]` (admin-only; claims "the OWNER affixed this", consumed by ABAC as `pinned_labels_required`). **Hierarchical**: `expand_label_segments` (`domain/item.py:53`) turns `project:pegasus` into `{project, project:pegasus}` | repeated `?label=` |
| **project docs** (`api/routers/projects.py`) | a single required `label: str` (model L69, write L487, blob form L507) | `?label=` — one exact value (L343) |
| **objects** (`api/routers/objects.py`) | **none** | `?path_prefix=` only |

The object store is the sharp edge, and it also **advertises an API it does not have**: the
module docstring (L21) documents `PUT /api/v1/objects (multipart: file, path[,
content_type, labels])`, but `put_object` (L194) takes only `file`, `path` and
`content_type`. `labels` appears nowhere else in the file. `list_objects`
(`storage/postgres_store/objects.py:90`) returns `record_id, path, size, content_type,
etag, workspace_uuid` — no labels to filter on even client-side.

## Why it matters

An object's only organising axis is its path. So the path has to encode both **where a
thing belongs** and **what it is** — and since renaming a path means physically moving
the object, that conflation is expensive to get wrong. Cross-cutting questions ("every
template, regardless of customer") need a parallel path root instead of a filter.

For any integrator the stale docstring is worse than the gap: it invites a design that
silently drops the labels it sends.

## Proposal

Generalise the **items** model — it is the richest, already battle-tested, and already
integrated with ABAC:

1. **objects** — accept `labels` on `PUT` (as the docstring already promises), return them
   from `/objects/list`, filter with repeated `?label=`.
2. **project docs** — widen the single `label: str` to `labels: list[str]`, still
   accepting a bare string so existing callers keep working.
3. Keep `pinned_labels` semantics wherever ABAC depends on owner-affixed claims.
4. Failing 1, at minimum **fix the objects docstring** so it stops promising labels.

## Scope note

This is a **generic** capability — "anything stored can be labelled" carries no
app-specific concept, so floor rule 6 (*apps detached from core*) does not bar it from
core. It is not small, though: three stores plus an ABAC surface.

## Who is waiting on it

Nobody, strictly. nSight's storage seam is being designed with `labels` as an optional
passthrough: it filters by path prefix today and starts filtering by label if this lands,
with no call-site changes. So this is an improvement to schedule, not a blocker.
