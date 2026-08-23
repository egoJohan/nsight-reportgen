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

`resolve()` wraps `load_style_spec` + `build_spec` behind an
`lru_cache(maxsize=16)` keyed on `(path, st_size, st_mtime_ns)`. A re-uploaded
template writes a different file (`_preview_template` already rewrites the temp
copy when the size differs), so the key busts itself; nothing has to remember to
invalidate.

Both callers change to `resolve()`: the preview path
(`routes_questions.py:1407,1463`) and the deck path (`routes_render.py:171`).
`slide_chrome.py` stops calling `build_spec` at its three sites and reads the
resolved spec that travels with the style.

A 60-slide deck walks the template once instead of 60 times.

### 2. One producer registry

Work is declared, not hardcoded. One entry per kind of thing a slide needs:

```ts
type ProducerId = "title" | "bullets" | "chart";   // + whatever comes later

interface Producer {
  id: ProducerId;
  after: ProducerId[];                    // declared ordering
  fingerprint(ctx): string;               // what this output depends on
  storedFingerprint(ctx): string | null;  // what the existing output was made for
  run(ctx): Promise<ChartPatch | void>;
  onFailure: "continue" | "abort";
}
```

Adding a future task is one registry entry. Nothing else changes — not the
worker, not the queue, not the wizard.

**Staleness is one rule for every producer:**

```
needed(p) = p.storedFingerprint(ctx) === null
         || p.storedFingerprint(ctx) !== p.fingerprint(ctx)
```

| Producer  | applies to      | fingerprint                | stored as |
|-----------|-----------------|----------------------------|-----------|
| `title`   | every chart slide | `titleDataKey(chart)`    | `chart.slide_title_key` |
| `bullets` | themes (open-ended) slides | `question_ref`  | presence of `options.bullets` |
| `chart`   | every slide     | `previewContentKey(chart)` | the image's cache key |

Only automatic work belongs in the registry. "Shorten with AI"
(`StepConfigure.tsx:1217`) is a button the user presses, and stays one — it is
the worked example of how a later producer plugs in, should it ever become
automatic: give it a fingerprint over the category label set, a stored key on
the chart, and one registry entry. Note that `labelsPending` in the current
`aiPending` map is vestigial — nothing ever sets it true — and goes with the
rest of that machinery.

Two consequences worth stating, because both are properties the old code tried
to maintain by hand:

* A chart-type change moves `previewContentKey` but not `titleDataKey`, so the
  slide re-renders and the title is left alone.
* `previewContentKey` *contains* the title, so a title landing automatically
  makes the image stale. Ordering is enforced by the fingerprints themselves,
  and a late title re-renders its slide exactly once.

### 3. One function, run sequentially

```ts
async function producePreview(slideId: string): Promise<void> {
  for (const p of PRODUCERS) {              // declared order
    const ctx = readSlide(slideId);         // re-read every time — never a snapshot
    if (!ctx) return;                       // slide deleted while queued
    if (!needed(p, ctx)) continue;
    try {
      applyPatch(slideId, await p.run(ctx));
      markDone(slideId, p.id);
    } catch (e) {
      markFailed(slideId, p.id, p.fingerprint(ctx), e);
      if (p.onFailure === "abort") return;
    }
  }
}
```

The context is re-read before every producer, so `chart` computes
`previewContentKey` *after* `title` applied its patch, and a slide edited while
queued is never worked on from stale data.

### 4. Failure

Per slide, per producer: `pending | running | done | failed`, recording the
fingerprint the failure happened at.

* `title` and `bullets` are `onFailure: "continue"` — a failed LLM call does not
  block the image. The slide renders with its question-text fallback, as today.
* `chart` is `onFailure: "abort"` — nothing downstream pretends an image exists.
* A failure is recorded rather than retried in a loop, and is **not** marked
  done, so it stays retryable. It surfaces in the red warning button already
  above the preview, and retry re-enqueues just that producer.

### 5. The queue

`web/src/lib/previewQueue.ts` replaces both existing queues.

```ts
enqueue(slideId)     // dedupes by slideId; a queued slide is not queued twice
promote(slideId)     // clicked slide jumps to the head; a running one is left alone
isBusy()             // any producer running, anywhere
subscribe(fn)        // components read status via useSyncExternalStore
```

Entering Design enqueues the whole deck; clicking a slide promotes it to the
head of the queue. Concurrency is per producer kind rather than one global
number: the Design step's compositor renders are ~0.25 s and the queue is
LLM-bound, while the Preview step's LibreOffice renders remain the expensive
class. The old global 3 was sized for LibreOffice and is wrong for both.

### 6. What the wizard keeps

`ReportWizard` keeps exactly one job it does not delegate: it owns the draft.
The queue never mutates the draft — it emits patches through a single seam,
applied in a batch per tick, so 60 producers do not cause 60 renders.

Saving becomes one rule: **draft dirty AND `!queue.isBusy()` → debounced save**,
with a 90 s cap so a stranded producer can never mean the author's typing is
lost. This replaces the `aiSaveTick`/`aiPending`/`aiBusy` machinery.

### 7. Deleted

* `ReportWizard.tsx`: `titleQueue`, `titleActive`, `pumpTitles`, `runTitle`,
  `titlesAttempted`, `ensureTitles`, `aiPending` (including the never-set
  `labelsPending`), `aiBusy`, `clearAiPending`
* `api.ts`: `previewQueue`, `pumpPreview`, `serializePreview`,
  `setActivePreviewKey`
* `SlideTitleOverlay.tsx` — dead already
* The `titlePending` props threaded through `StepConfigure`, `ChartThumb` and
  `DeckPrefetch`

## Verification

**Backend (pytest):** `resolve()` returns a cached instance for a repeated path;
a template whose bytes change produces a fresh one; the resolved spec matches
what `load_style_spec` + `build_spec` produced before.

**Frontend** has no test runner, so it is verified by driving the real UI with
Playwright against the dev stack, as done on 2026-08-23. A session cookie is
minted with the backend's own `auth.session` module
(`scratchpad/mint_session.py`). Against a 60-slide report the acceptance
criteria are:

| Scenario | Expected |
|---|---|
| Open Design on a title-less report | 60 title calls, 60 renders, **1** save |
| Open Design on a fully titled report | 0 title calls, 0 saves |
| Change one chart's type | 1 render, **0** title calls |
| Edit a slide title by hand | 1 save, ~2 s later |
| Click an unrendered slide mid-warm-up | it renders next |
| LLM title fails | slide still renders; failure shown in the warning button |

Baseline for comparison, measured today: 60 titles → 17 saves before the
interim fix, 1 after; 28 saves observed in the original backend log.

## Out of scope

Named so they are not lost, and neither is part of this work:

* Previews do not survive a page reload — the client image cache is not
  persisted.
* The backend preview disk cache is salted per process, so a restart
  re-renders everything.
* bottom-2 / bottom-3 sorting, parked with failing tests at
  `tests/suite/unit/stats/test_bottom_box_sort.py`.
