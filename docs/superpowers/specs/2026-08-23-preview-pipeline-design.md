# Preview pipeline: one template, one queue, one function

**Status:** approved 2026-08-23

## The problem

Producing a slide preview is three jobs — resolve the template, generate the
AI parts, rasterise the image — and today all three run in separate systems
that do not know about each other. The symptoms the user reports are all the
same defect seen from different angles:

* *"There is lots of constant saving when entering Design"* — 60 slides
  produced 17–28 document writes, because saves were triggered by whichever
  async pass happened to finish.
* *"It seems like LLM is generating the titles after the first rendering"* —
  the title queue and the render queue are independent, so a slide rasterises,
  then its title lands, then it rasterises again.
* *"The phase buttons do not react"* — the render pool and the title pool each
  run three concurrent jobs, on a machine also serving the API.
* *"Why does preview regenerate all"* — nothing records what a given output was
  made for, so nothing can tell what is still valid.

Each fix so far has patched an interaction between the three systems. The
systems are the problem.

## What is actually there now

Verified by reading the code on 2026-08-23:

* **The template is re-derived on every render.** `_load_style_spec()`
  (`routes_questions.py:1407,1463`; `routes_render.py:171`) reopens the
  `.pptx`, walks every layout via `inspect_template`, re-harvests the profile
  via `extract_profile`, and re-measures font metrics in `build_spec` — which
  `slide_chrome.py` calls again at three more sites. Nothing is cached, so a
  60-slide deck does this 60 times.
* **There are two queues.** An HTTP render gate in `api.ts`
  (`previewQueue`/`pumpPreview`/`serializePreview`, concurrency 3, content-keyed,
  with a promote-on-click reserved slot) and a separate AI title queue in
  `ReportWizard.tsx` (`titleQueue`/`pumpTitles`/`runTitle`, concurrency 3).
* **The title is baked into the PNG on both render paths.** `render_title`
  selects *how* a slide is rasterised — compositor or LibreOffice — never what
  is on it (`routes_questions.py:1226-1234`). A title change therefore requires
  a re-render. `SlideTitleOverlay.tsx` is dead code; nothing imports it.
* **`titleDataKey` already excludes presentation.** Chart type, colours, sort
  order and template are deliberately out of it (`charts.ts:95-125`), so a
  chart-type change must not regenerate a title.
* **`previewContentKey` is a hand-maintained allow-list** of 25 fields
  (`queries.ts:364`). Every new ChartSpec field must be remembered there or the
  preview silently keeps showing the old image.

## Scope

This spec covers the pipeline **and** the open tickets that are really the same
work — each one is a chart edit whose whole difficulty is "what has to be
regenerated?", which is the question the pipeline answers:

| Ticket | Requirement | Why it belongs here |
|---|---|---|
| **d95QXiWI** — Akselien nimien editointi | P-C-27: title, subtitle, value names and **axis names** editable in Design | The last of the four is missing. It is a presentation edit: re-render, never regenerate the title. |
| **A9JtdqPZ** — Bottom-2 / Bottom-3 row summary | Row-summary options | Same class; tests already written and failing at `tests/suite/unit/stats/test_bottom_box_sort.py`. |

**Not in scope: 7tGYRb8n** (classifying-variable menu rule, P-C-12) — it needs a
definition session with nSight before any implementation. Worth noting for
whoever picks it up that `classifying_var` *is* in `titleDataKey`, so changing
it correctly regenerates the title; that ticket changes which variables are
offered, not what happens when one is chosen.

### Axis names (d95QXiWI)

Today `elements.axis_names` is a boolean that only styles tick-label fonts
(`elements.py:98-110`); no axis *title* text exists on either path.

* `axis_x_title: str = ""` and `axis_y_title: str = ""` on `ChartSpec`
  (`model/report.py`), empty meaning "no axis title", which is today's look.
* Two text fields in the Design panel beside the existing title/subtitle ones.
* Rendered on **both** paths, because a preview must match its slide: native
  via `chart.value_axis.axis_title` / `category_axis.axis_title` in
  `render/elements.py`, and image via `ax.set_xlabel` / `ax.set_ylabel` in the
  matplotlib renderers, styled from the resolved template spec like all other
  furniture. Chart families with no axes (pie, doughnut, radar) ignore both.
* The existing `elements.axis_names` toggle keeps governing axis text: with it
  off, axis titles are not drawn even when set, so one control still means
  "no axis text on this slide".

## Design

### 1. The template is resolved once per template

New `src/reportbuilder/render/template_cache.py`:

```python
@dataclass(frozen=True)
class ResolvedTemplate:
    style: TemplateStyleSpec   # slots, chart layout index, palette
    spec:  TemplateSpec        # ground, ink, title/subtitle font + size + colour

def resolve(template_path: str) -> ResolvedTemplate:
    """Everything a render needs to know about a template. Cached."""
```

`resolve()` stats the file and calls an `lru_cache(maxsize=16)`'d inner function
keyed on `(path, st_size, st_mtime_ns)`. Two callers change to it — the preview
path (`routes_questions.py:1407,1463`) and the deck path
(`routes_render.py:171`).

**`build_spec` is called once, here, and never again.** Today
`slide_chrome.py` calls it per slide at three sites (`:504`, `:513`, `:717`),
passing a font it derives per slide from the title placeholder's inheritance
chain (`_inherited_title_font`). But every chart slide is built from the SAME
layout — `style.chart_layout_index` — so that font is a property of the
template, and deriving it per slide is pure waste: it re-loads a TTF through
PIL inside `size_for_cap_height` every time. `resolve()` walks that chain once,
on the layout's own title placeholder, and builds the spec from it. The
resolved spec travels with the style, so the three call sites become reads.

That is also why there is no separate font-metric cache: with the spec built
once per template there is nothing left to cache.

Concurrent first calls may compute twice under FastAPI's threadpool. That is
harmless: the result is a value, not a resource.

**A pre-existing bug this inherits, and must fix.** `_preview_template` only
rewrites its temp copy when `not f.exists() or f.stat().st_size != len(blob)`
(`routes_questions.py:1330`), so a re-uploaded template that happens to be the
same byte length is never written — and would now also never be re-resolved.
Key the temp file on a content hash of the blob instead of its size.

A 60-slide deck then walks the template once instead of 60 times.

### 2. Fingerprints, and which list a field belongs on

Every producer answers one question: *is what I made still valid?* It does that
by comparing the fingerprint of its inputs now against the fingerprint stored
with its output.

```
needed(p) = p.storedFingerprint(ctx) === null
         || p.storedFingerprint(ctx) !== p.fingerprint(ctx)
```

The two fingerprints are built by **opposite** rules, and the asymmetry is the
point:

* **The image fingerprint is a deny-list.** It hashes the whole `ChartSpec`
  minus the five fields that provably cannot change pixels — `slide_id` and
  `compare_group` (identity/provenance), `slide_title_key` (the title
  producer's own bookkeeping), `template_slot` and `excluded` (deck placement,
  not content) — plus the render context: template ref, report id, grouping and
  render mode. `template_slot` matters especially: it is rewritten by
  `normalizeSlots` on every reorder — `template_slot: \`s${i + 1}\`` for every
  chart in the list (`charts.ts:514`) — so hashing it would re-render all 60
  slides when the user drags one.
  Anything new — `axis_x_title`, a future field nobody has thought of — makes
  the image stale automatically. Getting this wrong costs one extra render;
  getting an allow-list wrong costs a silently stale preview that looks like the
  renderer is broken. Today's 25-field allow-list at `queries.ts:364` is
  replaced.
* **The title fingerprint stays an allow-list** — `titleDataKey`, unchanged.
  Here the costs invert: an over-broad key means needless LLM calls, visible
  churn and money, while a missed field means a title that is merely a bit
  stale. Presentation stays out by construction.

**The rule for anyone adding a chart field:** it lands in the image fingerprint
automatically. Add it to `titleDataKey` **only** if it changes what the data
*says*, not how it looks. `axis_x_title` and the bottom-2/3 row summary are both
presentation, so neither goes in — and both re-render without touching a title.

| Producer  | applies to | fingerprint | stored as |
|---|---|---|---|
| `title` | every chart slide | `titleDataKey(chart)` | `chart.slide_title_key` |
| `bullets` | themes (open-ended) slides | `question_ref` | presence of `options.bullets` — deliberately generate-once, as today |
| `chart` | every slide, special ones included | image fingerprint | the queue's completed-fingerprint map |

Two properties fall out, both of which the old code tried to maintain by hand:
a chart-type change moves the image fingerprint but not `titleDataKey`, so the
slide re-renders and the title is left alone; and because the image fingerprint
covers the whole spec — title included — a title landing makes its own image
stale, so ordering enforces itself and a late title re-renders its slide exactly
once.

### 3. One producer registry

Work is declared, not hardcoded — an ordered array, one entry per kind of work:

```ts
type ProducerId = "title" | "bullets" | "chart";   // + whatever comes later

interface Producer {
  id: ProducerId;
  fingerprint(ctx): string;
  storedFingerprint(ctx): string | null;
  run(ctx): Promise<ChartPatch | void>;
  onFailure: "continue" | "abort";
}

const PRODUCERS: Producer[] = [title, bullets, chart];  // order is the order
```

Adding a future task is one entry. Nothing else changes — not the worker, not
the queue, not the wizard.

Only automatic work belongs here. "Shorten with AI"
(`StepConfigure.tsx:1217`) is a button the user presses and stays one; it is the
worked example of how a later producer plugs in, should it ever become
automatic. `labelsPending` in the current `aiPending` map is vestigial —
nothing ever sets it true — and goes with the rest of that machinery.

### 4. One function, run sequentially

```ts
async function producePreview(slideId: string): Promise<void> {
  for (const p of PRODUCERS) {
    const ctx = readSlide(slideId);      // re-read every time — never a snapshot
    if (!ctx) return;                    // slide deleted while queued
    if (!needed(p, ctx)) continue;
    const fp = p.fingerprint(ctx);       // capture what we are about to satisfy
    try {
      applyPatch(slideId, await p.run(ctx));
      markDone(slideId, p.id, fp);       // store THAT fingerprint, not a re-read one
    } catch (e) {
      markFailed(slideId, p.id, fp, e);
      if (p.onFailure === "abort") return;
    }
  }
  if (PRODUCERS.some((p) => needed(p, readSlide(slideId)))) enqueue(slideId);
}
```

Three details carry the correctness:

* The context is re-read before every producer, so `chart` fingerprints *after*
  `title` applied its patch, and a slide edited mid-run is never worked from
  stale data. **`readSlide` must therefore read the queue's own working copy,
  not React state.** Patches are flushed to the wizard in batches (§7), so a
  producer reading React state would see the chart as it was *before* the
  previous producer wrote to it: `chart` would fingerprint against the old
  title, render, and the tail re-check would immediately find the title changed
  and re-enqueue — forever. The queue applies each patch to its working copy
  synchronously and flushes to React separately; producers read their own
  writes.

  The working copy is an *overlay*, not a second document: `readSlide` returns
  the draft (via `slideSource`) merged with whatever patches this queue has
  applied but not yet flushed, and a flush drops what it wrote. So the overlay
  can never shadow a later user edit — it is empty again the moment the draft
  holds the same values. A title patch racing a hand-edit of that same field
  resolves the way it does today: hand-typed clears `slide_title_key`, and
  whichever write lands last wins.
* `markDone` stores the fingerprint captured at the start of that producer —
  never one re-read afterwards, which would record work never actually done.
* The tail re-check catches an edit that arrived while the slide was running,
  and re-enqueues rather than leaving a stale output marked valid.

### 5. Failure

Per slide, per producer: `pending | running | done | failed`, recording the
fingerprint the failure happened at.

* `title` and `bullets` are `onFailure: "continue"` — a failed LLM call does not
  block the image. The slide renders with its question-text fallback, as today.
* `chart` is `onFailure: "abort"` — nothing downstream pretends an image exists.
* A failure is recorded rather than retried in a loop, and is **not** marked
  done, so it stays retryable. It surfaces in the red warning button already
  above the preview, and retry re-enqueues just that producer.

### 6. The queue

`web/src/lib/previewQueue.ts` replaces both existing queues.

```ts
enqueue(slideId)     // dedupes by slideId; a queued slide is not queued twice
promote(slideId)     // move to the head; no-op if running or already done
isBusy()             // any producer running, anywhere
subscribe(fn)        // components read status via useSyncExternalStore
```

The queue is a module-level singleton, not React state, so it survives step
changes (it does not survive a reload — see Out of scope). It is **keyed by
report**: opening a different report calls `reset(reportId)`, or one report's
statuses would be read as another's.

Two seams connect it to the wizard, registered on mount, so the queue never
imports React and the wizard never reaches into the queue:

```ts
setSlideSource(fn)  // how the queue reads the current draft
setPatchSink(fn)    // where patches go; the wizard applies them to the draft
```

It owns one authoritative store: `Map<slideId, Map<ProducerId, {status, fingerprint}>>`,
plus the working copy §4 depends on.
Image bytes still live in the React Query cache (keyed by the image fingerprint,
`staleTime: Infinity`), so existing consumers keep working and a stale image is
simply never looked up.

Entering Design enqueues the whole deck, and the wizard re-enqueues it whenever
the chart list changes, so a slide added later is picked up; `enqueue` dedupes
and `needed()` filters, so re-enqueueing a settled deck costs nothing. Clicking
a slide promotes it. Because
the Design preview and the Preview step now show the *same* image — the user's
requirement that "we need to use exactly the same slides for both" — there is
one `chart` producer and one image per slide, not one per step.

Concurrency is per producer kind rather than one global number. The old 3 was
sized for LibreOffice (~300 MB per process); the Design step now uses the
compositor at ~0.25 s, so the queue is LLM-bound, and the two kinds should not
share a limit.

### 7. What the wizard keeps

`ReportWizard` keeps exactly one job it does not delegate: it owns the draft.
The queue never mutates the draft — it emits patches through a single seam,
applied in a batch per tick, so 60 producers do not cause 60 renders.

Saving becomes one rule: **draft dirty AND `!queue.isBusy()` → debounced save**,
with a 90 s cap so a stranded producer can never mean the author's typing is
lost. This replaces the `aiSaveTick`/`aiPending`/`aiBusy` machinery.

### 8. Deleted

* `ReportWizard.tsx`: `titleQueue`, `titleActive`, `pumpTitles`, `runTitle`,
  `titlesAttempted`, `ensureTitles`, `aiPending` (including the never-set
  `labelsPending`), `aiBusy`, `clearAiPending`
* `api.ts`: `previewQueue`, `pumpPreview`, `serializePreview`,
  `setActivePreviewKey`
* `queries.ts`: `previewContentKey`'s 25-field allow-list
* `SlideTitleOverlay.tsx` — dead already
* The `titlePending` props threaded through `StepConfigure`, `ChartThumb` and
  `DeckPrefetch`

## Shipping order

The backend half stands alone and lands first: the template cache and the
temp-file hash fix are invisible to the frontend beyond being faster, and axis
titles are additive (empty string = today's look). The frontend rewrite —
registry, queue, wizard — is one change that cannot be half-done, because it
deletes the two queues it replaces.

## Verification

**Backend (pytest).** `resolve()` returns the same instance for a repeated path
and a fresh one when the file's bytes change; the resolved spec matches what
`load_style_spec` + `build_spec` produced before; a same-length re-upload is
picked up (the temp-file hash fix); axis titles render on both paths and are
ignored by pie/doughnut/radar.

**Frontend unit tests (new).** The fingerprint functions are the heart of this
design and are pure, so they get real tests rather than a manual pass — the
repo has no frontend runner today, so this adds **vitest** for pure modules
only, no component rendering. Cases: a chart-type change moves the image
fingerprint and not `titleDataKey`; adding `axis_x_title` moves the image
fingerprint (the deny-list property, which is the whole point); `titleDataKey`
is stable across colour, sort, template and row-summary edits; `needed()` is
false for an untouched slide.

**End-to-end**, driving the real UI with Playwright against the dev stack, as
done on 2026-08-23 — a session cookie is minted with the backend's own
`auth.session` module. Against a 60-slide report:

| Scenario | Expected |
|---|---|
| Open Design on a title-less report | 60 title calls, 60 renders, **1** save |
| Open Design on a fully titled report | 0 title calls, 0 renders, 0 saves |
| Change one chart's type | 1 render, **0** title calls |
| Edit an axis name | 1 render, **0** title calls |
| Edit a slide title by hand | 1 render, 1 save, no title call |
| Click an unrendered slide mid-warm-up | it renders next |
| LLM title fails | slide still renders; failure shown in the warning button |
| Design → Preview | no re-render; the same images |

Baseline measured on 2026-08-23: 60 titles → 17 saves before the interim fix, 1
after; 28 saves in the original backend log.

## Out of scope

Named so they are not lost, and none is part of this work:

* Previews do not survive a page reload — the client image cache is not
  persisted.
* The backend preview disk cache is salted per process, so a restart
  re-renders everything.
* 7tGYRb8n, the classifying-variable menu rule, which needs definition first.
