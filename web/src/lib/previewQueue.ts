/**
 * One queue, one sequential function per slide.
 *
 * Producing a slide preview is three jobs — write the headline, write the theme
 * bullets, rasterise the image — and they used to run in two independent
 * queues that did not know about each other. A slide rendered, then its title
 * landed, then it rendered again; saves fired from whichever pass finished
 * first; and nothing recorded what a given output had been made FOR, so nothing
 * could tell what was still valid.
 *
 * Here, each slide runs one function that walks an ordered registry of
 * producers. A producer says what its output depends on (a fingerprint) and
 * what the existing output was made for (a stored fingerprint); it runs when
 * those disagree. Adding a future kind of work is one registry entry — the
 * worker, the queue and the wizard do not change.
 *
 * The queue is a module-level singleton, so it survives step changes within a
 * report. It does NOT survive a reload, which is why previews are re-rendered
 * after one.
 */
import type { ChartSpec } from "./api";
import { imageFingerprint, type RenderContext } from "./previewFingerprint";

export type ProducerId = "title" | "bullets" | "chart";
export type Status = "pending" | "running" | "done" | "failed";

export interface ProducerCtx {
  slideId: string;
  /** The slide as it is RIGHT NOW: the draft, plus this queue's own unflushed
   *  patches. Producers must read their own writes — see `readSlide`. */
  chart: ChartSpec;
  ctx: RenderContext;
  /** What this producer is about to satisfy, computed once by the worker. */
  fingerprint: string;
}

export interface Producer {
  id: ProducerId;
  fingerprint(c: Omit<ProducerCtx, "fingerprint">): string;
  /** What the existing output was made for, or null when there is none.
   *  Returning `c.fingerprint` means "already up to date, leave it alone". */
  storedFingerprint(c: ProducerCtx): string | null;
  run(c: ProducerCtx): Promise<Partial<ChartSpec> | void>;
  /** Whether the author overtook this work while it was running: `before` is the
   *  slide the run started from, `after` the slide as it is now. True means throw
   *  the result away. A model round trip is seconds long, and a person editing
   *  the same field in that window must win — they are looking at it. */
  supersededBy?(before: ChartSpec, after: ChartSpec): boolean;
  onFailure: "continue" | "abort";
}

// ── The seams to the wizard ──────────────────────────────────────────────────
// Registered on mount. The queue never imports React, and the wizard never
// reaches into the queue's internals.

type SlideSource = (slideId: string) => ChartSpec | null;
type PatchSink = (slideId: string, patch: Partial<ChartSpec>) => void;

let slideSource: SlideSource = () => null;
/** Every slide in the report, in order. Told to the queue by the wizard, so a
 *  context change can refill the queue with the whole deck without asking
 *  anyone. */
let deck: string[] = [];
let patchSink: PatchSink = () => {};
let renderContext: RenderContext = {
  templateRef: "",
  reportId: "",
  groupingKey: "{}",
  renderTitle: false,
};

export function setSlideSource(fn: SlideSource) {
  slideSource = fn;
}

/** The slides this report has, in order. */
export function setDeck(slideIds: string[]) {
  deck = slideIds.filter(Boolean);
}
export function setPatchSink(fn: PatchSink) {
  patchSink = fn;
}
/** Bumped whenever the context every slide is drawn in changes — a new
 *  template, a new grouping. Work started under an older one is abandoned
 *  rather than finished: a picture of the previous template is not worth the
 *  wait, and finishing it would put a stale image in the cache for a
 *  fingerprint nobody is asking for any more. */
let contextGeneration = 0;

export function setRenderContext(ctx: RenderContext) {
  if (JSON.stringify(ctx) === JSON.stringify(renderContext)) return;
  const before = renderContext;
  const wasQueued = queue.length;
  const wasRunning = running.size;
  renderContext = ctx;

  // Changing the template (or the grouping) restyles the whole deck, so the
  // queue starts again, deliberately and in one place:
  //
  //   stop  — work in flight was started for the previous template, so bumping
  //           the generation makes it abandon itself when it returns;
  //   clear — everything queued was queued for that template too;
  //   refill — every slide, in order, from the top.
  //
  // Each slide then decides for itself what it actually needs, which is where
  // "do not rewrite a headline that is already correct" lives: a title is about
  // the DATA, and the template did not change the data, so the title producer
  // finds itself up to date and only the picture is redrawn.
  //
  // Doing this here rather than leaving it to whichever component noticed is
  // the point. It used to be spread across an effect, a debounce and a tail
  // re-check, and slides fell between them.
  restartDeck(
    `template "${before.templateRef}" -> "${ctx.templateRef}"; ` +
    `dropped ${wasQueued} queued, ${wasRunning} running will abandon`
  );
}

/** Stop, clear, and re-queue the whole deck.
 *
 *  Stop  — work in flight was started for the previous state, so bumping the
 *          generation makes it abandon itself when it returns.
 *  Clear — everything queued was queued for that state too.
 *  Refill — every slide, in order, from the top.
 *
 *  Each slide then decides for itself what it actually needs, which is where
 *  "do not rewrite a headline that is already correct" lives: a title is about
 *  the DATA, and a template change did not change the data, so the title
 *  producer finds itself up to date and only the picture is redrawn.
 */
export function restartDeck(reason: string) {
  contextGeneration += 1;
  queue = [];
  queued = new Set();
  say("restart", { detail: `gen=${contextGeneration} ${reason}; re-queueing ${deck.length} slides` });
  for (const slideId of deck) enqueue(slideId);
  pump();
}

// ── State ────────────────────────────────────────────────────────────────────

interface Entry {
  status: Status;
  fingerprint: string | null;
  error?: unknown;
}

let statuses = new Map<string, Map<ProducerId, Entry>>();
/** Patches applied but not yet reflected in what `slideSource` returns. */
let overlay = new Map<string, Partial<ChartSpec>>();
let queue: string[] = [];
let queued = new Set<string>();
/** Slides with a pass in flight. Enqueueing one again is a no-op: the pass ends
 *  by re-checking its own fingerprints, which is what catches an edit that
 *  arrived mid-run. Without this, every keystroke during a render started a
 *  second pass over the same slide. */
let running = new Set<string>();
/** Slides that asked to be queued again WHILE they were running.
 *
 *  `enqueue` refuses a running slide on purpose — an edit arriving mid-run is
 *  caught by the pass's own tail re-check, so queueing it twice would just do
 *  the work twice. But that same refusal silently swallowed the two calls that
 *  come FROM inside a run: the tail re-check itself, and the abandon path when
 *  the template changes under it. A slide abandoned mid-render was therefore
 *  never picked up again, and sat unfinished for ever — which is exactly what
 *  switching templates looked like. These are remembered and queued the moment
 *  the pass ends. */
let requeue = new Set<string>();
/** (slide, producer, fingerprint) triples that have already had their one
 *  retry after a failure. Bounds the retry to exactly one per attempt, and
 *  is cleared with the rest of the session state. */
let retried = new Set<string>();
let active = 0;
let concurrency = 4;
let currentReportId = "";
const listeners = new Set<() => void>();
let idleWaiters: Array<() => void> = [];

function notify() {
  for (const fn of listeners) fn();
}

export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Any producer running or waiting to run. Drives the wizard's save rule. */
export function isBusy(): boolean {
  return active > 0 || queue.length > 0;
}

/** This slide's statuses as a stable STRING.
 *
 * useSyncExternalStore compares snapshots by identity, so a hook returning a
 * fresh object every render would re-render for ever. The string only changes
 * when a status does.
 */
export function statusKeyOf(slideId: string): string {
  const forSlide = statuses.get(slideId);
  if (!forSlide) return "";
  const parts: string[] = [];
  for (const [id, e] of forSlide) parts.push(`${id}:${e.status}`);
  return parts.join(",");
}

export function statusOf(slideId: string): Partial<Record<ProducerId, Status>> {
  const out: Partial<Record<ProducerId, Status>> = {};
  for (const [id, e] of statuses.get(slideId) ?? []) out[id] = e.status;
  return out;
}

/** Which producers failed on this slide, and why — for the warning button. */
export function failuresOf(slideId: string): Array<{ id: ProducerId; error: unknown }> {
  const out: Array<{ id: ProducerId; error: unknown }> = [];
  for (const [id, e] of statuses.get(slideId) ?? []) {
    if (e.status === "failed") out.push({ id, error: e.error });
  }
  return out;
}

/** Start over. Statuses and patches are per EDITING SESSION — reading one
 *  report's as another's would show finished work that was never done, and
 *  reading the last session's as this one's is just as wrong.
 *
 *  This used to return early when the report id was unchanged, which made
 *  reopening the same report keep the previous session's overlay. The overlay
 *  normally cleans itself up once the draft catches up, but a patch written
 *  moments before the editor closes never gets that far — its React state
 *  update dies with the unmount — and that dead patch was then laid back over
 *  a draft freshly fetched from the server. The caller decides when a session
 *  starts; this just does as it is told. */
export function reset(reportId: string) {
  say("reset", { detail: `report ${currentReportId || "(none)"} -> ${reportId}` });
  currentReportId = reportId;
  statuses = new Map();
  overlay = new Map();
  queue = [];
  queued = new Set();
  requeue = new Set();
  retried = new Set();
  notify();
}


// ── Tracing ──────────────────────────────────────────────────────────────────
// Every decision this queue makes, in order, with the reason.
//
// The queue is asynchronous, ordered, and its bugs are all of the form "this
// slide never finished" — which is invisible from outside: the screen simply
// shows an old picture for ever. Working out WHY needs the sequence, so the
// sequence is recorded rather than reconstructed.
//
// In the browser: `window.__previewQueue.trace()` for the table,
// `window.__previewQueue.state()` for what is queued/running right now, and
// `localStorage.previewQueueDebug = "1"` to mirror it to the console live.

export interface TraceEvent {
  /** ms since the trace started */
  t: number;
  event: string;
  slideId?: string;
  producer?: ProducerId;
  detail?: string;
  /** queued / running / active, at the moment of the event */
  q?: string;
}

/** Fingerprints are long JSON strings; the trace only needs them to be
 *  comparable at a glance. */
function short(fp: string): string {
  let h = 0;
  for (let i = 0; i < fp.length; i++) h = (h * 31 + fp.charCodeAt(i)) | 0;
  return (h >>> 0).toString(16).padStart(8, "0");
}

const TRACE_CAP = 4000;
let trace: TraceEvent[] = [];
const traceStart = typeof performance !== "undefined" ? performance.now() : 0;

function say(event: string, data: Omit<TraceEvent, "t" | "event"> = {}) {
  const now = typeof performance !== "undefined" ? performance.now() : 0;
  const e: TraceEvent = {
    t: Math.round(now - traceStart),
    event,
    ...data,
    q: `q${queue.length}/r${running.size}/a${active}`,
  };
  trace.push(e);
  // A cap, because this runs for the life of the tab: the last few thousand
  // events are what a diagnosis needs, and an unbounded array is a leak.
  if (trace.length > TRACE_CAP) trace = trace.slice(-TRACE_CAP / 2);
  if (debugToConsole()) {
    // eslint-disable-next-line no-console
    console.debug(
      `[queue ${e.t}ms ${e.q}] ${event}`,
      e.slideId ?? "",
      e.producer ?? "",
      e.detail ?? ""
    );
  }
}

function debugToConsole(): boolean {
  try {
    return typeof localStorage !== "undefined"
      && localStorage.getItem("previewQueueDebug") === "1";
  } catch {
    return false;
  }
}

/** A component is asking for a slide's picture under this fingerprint.
 *
 *  Recorded because the failure that is hardest to see from outside is a
 *  MISMATCH: the queue renders every slide, reports itself finished, and the
 *  screen stays blank because the thing displaying is keyed on something
 *  slightly different. Both halves are in the trace now, so they can be
 *  compared instead of reasoned about.
 */
export function noteWanted(slideId: string, fingerprint: string, hasImage: boolean) {
  say("wanted", {
    slideId,
    detail: `fp=${short(fingerprint)} ${hasImage ? "hit" : "MISS"}`,
  });
}

/** The recorded sequence. */
export function getTrace(): TraceEvent[] {
  return trace;
}

export function clearTrace() {
  trace = [];
}

/** What the queue is doing right now — the answer to "is it stuck?". */
export function snapshot() {
  const pending: Record<string, string> = {};
  for (const [slideId, byProducer] of statuses) {
    const parts: string[] = [];
    for (const [id, e] of byProducer) if (e.status !== "done") parts.push(`${id}:${e.status}`);
    if (parts.length) pending[slideId] = parts.join(",");
  }
  // What each slide's picture was last rendered FOR. The failure that is
  // invisible from outside is a mismatch — the queue reports itself finished
  // and the screen stays blank because the two are keyed on different things —
  // so this is here to be compared against what a component asks for.
  const renderedFor: Record<string, string> = {};
  for (const [slideId, byProducer] of statuses) {
    const e = byProducer.get("chart");
    if (e?.fingerprint) renderedFor[slideId] = short(e.fingerprint);
  }
  return {
    queued: [...queued],
    running: [...running],
    requeue: [...requeue],
    active,
    concurrency,
    generation: contextGeneration,
    context: renderContext,
    unfinished: pending,
    slidesTracked: statuses.size,
    renderedFor,
    knows: (slideId: string) => statuses.has(slideId),
  };
}

// ── Reading and writing a slide ──────────────────────────────────────────────

function readSlide(slideId: string): ChartSpec | null {
  const base = slideSource(slideId);
  if (!base) return null;
  const pending = overlay.get(slideId);
  if (!pending) return base;
  // Drop overlay keys the draft has caught up on, so a patch cannot shadow a
  // later edit by the author to the same field.
  for (const k of Object.keys(pending)) {
    const a = (base as unknown as Record<string, unknown>)[k];
    const b = (pending as Record<string, unknown>)[k];
    if (JSON.stringify(a) === JSON.stringify(b)) delete (pending as Record<string, unknown>)[k];
  }
  if (!Object.keys(pending).length) {
    overlay.delete(slideId);
    return base;
  }
  return { ...base, ...pending };
}

function applyPatch(slideId: string, patch: Partial<ChartSpec>) {
  if (!patch || !Object.keys(patch).length) return;
  // Synchronously into the overlay, so the NEXT producer in this slide's run
  // sees it. React state does not update until a re-render, and the image
  // producer fingerprints the title the title producer just wrote — reading
  // React state here would fingerprint the old title, render, then find the
  // title changed and re-enqueue, for ever.
  overlay.set(slideId, { ...(overlay.get(slideId) ?? {}), ...patch });
  patchSink(slideId, patch);
}

function setStatus(slideId: string, id: ProducerId, status: Status,
                   fingerprint: string | null = null, error?: unknown) {
  const forSlide = statuses.get(slideId) ?? new Map<ProducerId, Entry>();
  forSlide.set(id, { status, fingerprint, error });
  statuses.set(slideId, forSlide);
  notify();
}

function completedFingerprint(slideId: string, id: ProducerId): string | null {
  const e = statuses.get(slideId)?.get(id);
  return e && e.status === "done" ? e.fingerprint : null;
}

// ── The registry ─────────────────────────────────────────────────────────────

let PRODUCERS: Producer[] = [];

/** Install the real producers. Done by producers.ts so this module stays free
 *  of api/ imports and remains testable on its own. */
export function setProducers(ps: Producer[]) {
  PRODUCERS = ps;
}

export { completedFingerprint };

/** Was this thrown because the work was called off, rather than because it went
 *  wrong? The client cancels a fetch nobody is observing any more, which is the
 *  normal consequence of the author changing the template mid-render. */
function isCancellation(e: unknown): boolean {
  const name = (e as { name?: string } | null)?.name ?? "";
  const msg = e instanceof Error ? e.message : String(e ?? "");
  return (
    name === "CancelledError" ||
    name === "AbortError" ||
    /cancel|abort/i.test(msg)
  );
}

function needed(p: Producer, base: Omit<ProducerCtx, "fingerprint">): ProducerCtx | null {
  const fingerprint = p.fingerprint(base);
  const c: ProducerCtx = { ...base, fingerprint };
  const stored = p.storedFingerprint(c);
  return stored === null || stored !== fingerprint ? c : null;
}

// ── The one function ─────────────────────────────────────────────────────────

async function producePreview(slideId: string): Promise<void> {
  /** What each producer was asked to satisfy on this pass. */
  const handled = new Map<ProducerId, string>();
  const startedUnder = contextGeneration;
  /** The author changed the template (or the grouping) while this was running.
   *  Whatever comes back describes the old one. */
  const abandoned = () => contextGeneration !== startedUnder;

  for (const p of PRODUCERS) {
    const chart = readSlide(slideId);
    if (!chart) {
      say("slide-gone", { slideId, detail: "deleted while queued" });
      statuses.delete(slideId);
      notify();
      return;
    }
    const c = needed(p, { slideId, chart, ctx: renderContext });
    if (!c) {
      // Not needed after all: clear the pending mark set at enqueue, or the
      // slide would sit showing "updating" for work nobody is going to do.
      say("skip", { slideId, producer: p.id, detail: "already up to date" });
      if (statuses.get(slideId)?.get(p.id)?.status === "pending") {
        setStatus(slideId, p.id, "done", p.fingerprint({ slideId, chart, ctx: renderContext }));
      }
      continue;
    }
    handled.set(p.id, c.fingerprint);
    say("run", { slideId, producer: p.id, detail: `fp=${short(c.fingerprint)}` });
    setStatus(slideId, p.id, "running", c.fingerprint);
    try {
      const patch = await p.run(c);
      if (abandoned()) {
        say("abandon", {
          slideId,
          producer: p.id,
          detail: `started under gen ${startedUnder}, now ${contextGeneration}`,
        });
        // Drop the result and start this slide again under the new context.
        // Recording it would cache a picture of the template the author just
        // moved away from, under a fingerprint nothing will ask for.
        setStatus(slideId, p.id, "pending", null);
        requeueAfterRun(slideId, "context changed under it");
        return;
      }
      const now = patch && p.supersededBy ? readSlide(slideId) : null;
      if (now && p.supersededBy!(chart, now)) {
        // The author changed this under us while the request was out. Their
        // version stands; ours is recorded as satisfied so nothing re-runs it
        // and overwrites them a second time.
        say("discard", { slideId, producer: p.id, detail: "author overtook it" });
        setStatus(slideId, p.id, "done",
                  p.fingerprint({ slideId, chart: now, ctx: renderContext }));
        continue;
      }
      if (patch) applyPatch(slideId, patch);
      // The fingerprint captured BEFORE the run, never one re-read after it:
      // re-reading would record work that was never done.
      setStatus(slideId, p.id, "done", c.fingerprint);
      say("done", { slideId, producer: p.id });
    } catch (e) {
      // A cancellation is not a failure.
      //
      // When the template changes, the components stop observing the old
      // fingerprint's query and the client cancels its in-flight fetch. That
      // arrives here as an error, and treating it as one was fatal: the slide
      // was marked failed, `onFailure: "abort"` stopped the pass, and because
      // that return skipped the tail re-check below, nothing ever queued the
      // slide again. Twenty slides of a sixty-slide deck ended a burst of
      // template switching stuck on "failed" with no picture — the "never
      // finishes" this whole queue was accused of.
      if (abandoned() || isCancellation(e)) {
        say("cancelled", { slideId, producer: p.id, detail: "superseded; will run again" });
        setStatus(slideId, p.id, "pending", null);
        requeueAfterRun(slideId, "its work was cancelled");
        return;
      }
      say("failed", {
        slideId,
        producer: p.id,
        detail: e instanceof Error ? e.message : String(e),
      });
      // One retry, then believe it. Most failures here are transient — the
      // backend restarting, a proxy timing out, a request that lost its
      // connection — and before this the slide simply stayed broken until the
      // author noticed and edited it, which they will not do for a slide they
      // are not looking at. Keyed on the fingerprint, so a genuinely broken
      // slide fails exactly twice and then stops rather than looping. It goes
      // to the BACK of the queue, which is also the delay.
      const attempt = `${slideId}|${p.id}|${c.fingerprint}`;
      if (!retried.has(attempt)) {
        retried.add(attempt);
        say("retry", { slideId, producer: p.id, detail: "first failure; trying once more" });
        setStatus(slideId, p.id, "pending", null);
        requeueAfterRun(slideId, "one retry after a failure");
        return;
      }
      setStatus(slideId, p.id, "failed", c.fingerprint, e);
      // Stop, and do NOT fall through to the tail re-check. Producers after
      // this one never ran, so they are absent from `handled`, and the tail
      // check reads "absent" as "changed" — which queues the slide again, to
      // fail again, for ever. (Work that was merely superseded is handled
      // above and does come back.)
      if (p.onFailure === "abort") return;
    }
  }

  // An edit that arrived WHILE this slide was running leaves it stale again, so
  // the pass ends by looking once more.
  //
  // Only a fingerprint that MOVED counts. "Still needed at the same
  // fingerprint" means the producer did not record its own output — a bug in
  // that producer — and re-enqueueing on it would spin this slide for ever,
  // which is precisely the class of failure this queue replaced. It gets
  // dropped here instead, leaving the producer's status visible as not-done.
  const chart = readSlide(slideId);
  if (!chart) return;
  const moved = PRODUCERS.some((p) => {
    const c = needed(p, { slideId, chart, ctx: renderContext });
    return c !== null && c.fingerprint !== handled.get(p.id);
  });
  if (moved) {
    requeueAfterRun(slideId, "changed while it ran");
  } else {
    say("settled", { slideId });
  }
}

// ── The queue ────────────────────────────────────────────────────────────────

/** Queue this slide again once the pass currently running it has ended.
 *
 *  For the queue's OWN two callers — the abandon path and the tail re-check —
 *  which both run inside a pass, when the slide is still marked running.
 *  `enqueue` drops a running slide on purpose, so those calls were silently
 *  swallowed: a render abandoned because the template changed under it was
 *  never picked up again and the slide sat unfinished for ever, which is
 *  exactly what switching templates looked like.
 *
 *  Not the same as `enqueue` refusing a running slide from OUTSIDE. There, the
 *  refusal is right: an edit arriving mid-run is caught by that pass's own tail
 *  re-check, and queueing it as well would do the work twice.
 */
function requeueAfterRun(slideId: string, why: string) {
  requeue.add(slideId);
  say("requeue-after-run", { slideId, detail: why });
}

export function enqueue(slideId: string) {
  if (!slideId || queued.has(slideId) || running.has(slideId)) return;
  queued.add(slideId);
  queue.push(slideId);
  say("enqueue", { slideId });
  // Mark it pending NOW. A slide waiting its turn behind fifty others is not
  // finished, and showing it as finished is why changing the template looked
  // like nothing had happened: the work was queued, the screen just never said
  // so. Which producers it will need is not known until it runs, so this is
  // deliberately about the SLIDE, not about any one producer.
  const forSlide = statuses.get(slideId) ?? new Map<ProducerId, Entry>();
  for (const p of PRODUCERS) {
    const e = forSlide.get(p.id);
    if (!e || e.status === "done") forSlide.set(p.id, { status: "pending", fingerprint: e?.fingerprint ?? null });
  }
  statuses.set(slideId, forSlide);
  notify();
  pump();
}

/** The slide the author just selected renders next. */
export function promote(slideId: string) {
  const i = queue.indexOf(slideId);
  if (i > 0) {
    queue.splice(i, 1);
    queue.unshift(slideId);
    say("promote", { slideId, detail: `from position ${i}` });
  }
  pump();
}

function pump() {
  while (active < concurrency && queue.length) {
    const slideId = queue.shift()!;
    queued.delete(slideId);
    running.add(slideId);
    active += 1;
    say("start", { slideId });
    notify();
    void producePreview(slideId).finally(() => {
      running.delete(slideId);
      active -= 1;
      if (requeue.delete(slideId)) {
        say("requeue", { slideId, detail: "asked for while it was running" });
        enqueue(slideId);
      }
      notify();
      if (!isBusy()) {
        const waiters = idleWaiters;
        idleWaiters = [];
        for (const w of waiters) w();
      }
      pump();
    });
  }
  if (!isBusy()) {
    const waiters = idleWaiters;
    idleWaiters = [];
    for (const w of waiters) w();
  }
}

/** Resolves when nothing is queued or running. */
export function whenIdle(): Promise<void> {
  if (!isBusy()) return Promise.resolve();
  return new Promise((resolve) => idleWaiters.push(resolve));
}

// ── Test seams ───────────────────────────────────────────────────────────────

export function __setProducersForTest(ps: Producer[]) {
  PRODUCERS = ps;
}
export function __setConcurrencyForTest(n: number) {
  concurrency = n;
}
export function __drainForTest(): Promise<void> {
  return whenIdle();
}
/** The context generation, for tests that need to make a fingerprint move when
 *  the template changes — which is what the real image fingerprint does. */
export function __generationForTest(): number {
  return contextGeneration;
}

export function __resetForTest() {
  currentReportId = "";
  statuses = new Map();
  overlay = new Map();
  queue = [];
  queued = new Set();
  running = new Set();
  requeue = new Set();
  retried = new Set();
  active = 0;
  contextGeneration = 0;
  trace = [];
  concurrency = 4;
  PRODUCERS = [];
}

export { imageFingerprint };

// ── The console handle ───────────────────────────────────────────────────────
// `window.__previewQueue` in any environment that has a window. Not gated to
// dev builds on purpose: the reports that matter come from someone using the
// real thing, and "reproduce it locally first" is how a queue bug survives.
declare global {
  interface Window {
    __previewQueue?: {
      state: () => ReturnType<typeof snapshot>;
      trace: () => TraceEvent[];
      table: () => void;
      clear: () => void;
      debug: (on?: boolean) => string;
    };
  }
}

if (typeof window !== "undefined") {
  window.__previewQueue = {
    state: snapshot,
    trace: getTrace,
    table: () => {
      // eslint-disable-next-line no-console
      console.table(
        getTrace().map((e) => ({
          "t(ms)": e.t,
          event: e.event,
          slide: e.slideId ?? "",
          producer: e.producer ?? "",
          "queue(q/r/a)": e.q ?? "",
          detail: e.detail ?? "",
        }))
      );
    },
    clear: clearTrace,
    debug: (on = true) => {
      try {
        localStorage.setItem("previewQueueDebug", on ? "1" : "0");
      } catch {
        /* private mode: the trace still records, it just does not mirror */
      }
      return on ? "logging queue events to the console" : "console logging off";
    },
  };
}
