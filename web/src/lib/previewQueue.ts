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
  /** The author pressed "draw this slide again". Everything that would decline
   *  the work has been cleared, INCLUDING the producer's own record of having
   *  done it — so a producer that reads through a cache must go past it, or the
   *  button hands back the same picture and appears to do nothing. */
  force?: boolean;
}

export interface Producer {
  id: ProducerId;
  /** Whether this producer has any work on this KIND of slide. Separate from
   *  "already done", because a forced pass deliberately ignores that one: a
   *  special slide has no question, so the title and bullets producers could
   *  only fail against it, twice, every time the author asked for a redraw. */
  applies?(c: Omit<ProducerCtx, "fingerprint">): boolean;
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
  /** This producer's work happens on the RENDER HOST's CPU, so no more of it
   *  may run at once than that host has cores.
   *
   *  The distinction exists because the other producers are the opposite kind
   *  of work: writing a headline is a round trip to a model, seconds long,
   *  spent waiting, costing the render host nothing. Holding both to the core
   *  count made a cold open pay its headlines strictly one after another —
   *  141s of the 162s a thirty-slide deck took, against 26s of actual drawing.
   *  Left false, a producer is assumed to be waiting on somebody else. */
  cpuBound?: boolean;
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
  // `enqueue` refuses with no report open, so this would be a no-op with a
  // misleading trace line. Say so and stop.
  if (!currentReportId) {
    say("restart", { detail: `${reason}; no report open, nothing to re-queue` });
    return;
  }
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
let retried = new Map<string, number>();
/** Retries scheduled but not yet due. Counted as outstanding work, or the queue
 *  would call itself idle in the gap between a failure and its next attempt and
 *  anything waiting for the deck would stop early. */
let pendingRetries = 0;

/** How long before the next attempt at a failure that may pass, in ms.
 *
 *  The spacing IS the fix. A 502 returns in milliseconds, so retrying at once
 *  spends every attempt inside the same outage: staging logged 116 failed
 *  renders in 7 seconds — 16-19 per second, against about one per second when
 *  healthy — while the backend was down for six. Both of a slide's attempts
 *  landed in that window, and it was then marked failed for good. The last step
 *  outlasts any deploy we do, so a deck rides one out untouched. */
const RETRY_BACKOFF_MS = [500, 1500, 4000, 10000, 20000];

/** The status an error carries, if any. Read by shape rather than by importing
 *  `ApiError`, so the queue stays independent of the API layer. */
function errorStatus(e: unknown): number | null {
  const s = (e as { status?: unknown } | null)?.status;
  return typeof s === "number" ? s : null;
}

/** Is this failure worth waiting out?
 *
 *  5xx, 408 and 429 are the service saying "not now"; a fetch that never landed
 *  (TypeError — the browser's shape for a dead connection) says it too. A 4xx,
 *  or a bug in a producer, will fail identically however long we wait, and
 *  keeps the single retry it always had. */
function isTransient(e: unknown): boolean {
  const status = errorStatus(e);
  if (status !== null) return status >= 500 || status === 408 || status === 429;
  const name = (e as { name?: unknown } | null)?.name;
  const msg = e instanceof Error ? e.message : "";
  return name === "TypeError" || /failed to fetch|networkerror|load failed/i.test(msg);
}
/** Slides a mounted component says it has no picture for, and how many times it
 *  has said so. Cleared the moment one reports a picture. */
let blankSince = new Map<string, number>();
/** Slides whose next pass must run whatever its producers claim is stored. */
let forceRedraw = new Set<string>();
/** How many times the screen may say "still blank" before we stop trying and
 *  show the author a failure instead. Three, because each attempt is a full
 *  render: enough to ride out a transient cause, few enough that a slide which
 *  genuinely cannot be drawn does not render for ever. */
const BLANK_ATTEMPTS = 3;
let active = 0;
/** How many slides to draw at once.
 *
 *  Sized to what the SERVER can actually draw in parallel, which it reports
 *  from its own core count — see `setConcurrency`. One, until it says
 *  otherwise: rendering is CPU-bound (LibreOffice -> PDF -> raster), so asking
 *  for more than the renderer has cores buys no throughput at all and
 *  multiplies what the author waits for. Measured on a 30-slide deck on one
 *  core: the whole deck took 47-49s at EVERY setting from 1 to 8, while the
 *  median wait for one slide went 2.9s -> 4.1s -> 6.4s -> 7.7s -> 11.0s ->
 *  14.8s. Four was costing 7.7s per slide to finish the deck no sooner.
 *
 *  Defaulting LOW is deliberate: the error is asymmetric. Too low on a big
 *  machine costs some throughput on a background warm; too high on a small one
 *  costs the author seconds on every single slide they look at. */
/** Slide passes in flight.
 *
 *  ONE, and the reason is the whole of this queue's history in one number.
 *
 *  A pass looks like it is spent waiting — a model writes a headline, a host
 *  draws a picture — so running several at once looks free. It is not. Both
 *  ends of that wait are served by ONE machine with ONE core: the backend
 *  prepares every headline request before the relay ever sees it, and draws
 *  every picture, and it is the same core doing both. Fan-out does not add
 *  capacity there; it divides it, and hands the author a longer wait for the
 *  one slide they are looking at.
 *
 *  Measured on a cold 30-slide deck, clicking a slide part-way through:
 *
 *      passes   click -> picture   deck warmed in
 *        1           5.8s              162s
 *        4          11.5s               76s
 *        8          20.0s               ~60s
 *
 *  The relay itself is blameless — eight concurrent calls to it each still
 *  returned in 4.5-4.8s. It is the single core in front of it: at four passes
 *  a headline call that costs 4.6s alone took 9.1s.
 *
 *  So the deck warms more slowly and every slide the author actually opens is
 *  twice as fast, which is the trade this product wants. The slide being
 *  looked at is exempt anyway — see `pump`, which gives it a slot of its own.
 */
let concurrency = 1;
/** Pictures being drawn at once. Reported by the server from the cores it is
 *  actually scheduled on (see `setRenderConcurrency`), because drawing is
 *  CPU-bound and asking for more than there are cores buys no throughput while
 *  multiplying what the author waits for: measured on one core, a 30-slide
 *  deck took 47-49s at every setting from 1 to 8 while the median wait for a
 *  single slide went 2.9s -> 7.7s -> 14.8s. */
let renderConcurrency = 1;
let rendersActive = 0;
let renderWaiters: Array<() => void> = [];

/** Run one piece of CPU-bound work, waiting for a turn on the render host. */
async function withRenderSlot<T>(fn: () => Promise<T>): Promise<T> {
  while (rendersActive >= renderConcurrency) {
    await new Promise<void>((resolve) => renderWaiters.push(resolve));
  }
  rendersActive += 1;
  try {
    return await fn();
  } finally {
    rendersActive -= 1;
    renderWaiters.shift()?.();
  }
}
let currentReportId = "";
/** The slide the author is looking at.
 *
 *  Held here rather than being told to the queue as a one-off promotion,
 *  because a promotion only orders the queue AS IT IS. The author selects a
 *  slide, it goes to the head and draws; then they type a headline into it,
 *  the wizard queues it again — and nothing says "this is still the slide they
 *  are looking at", so it went on the END, behind every slide they are not.
 *  Measured on a cold twenty-four slide deck: their own headline appeared 36.6s
 *  after they stopped typing, against 1.0s with nothing else queued. That is
 *  the whole of "the preview got slow when editing titles". */
let focused = "";
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
  return active > 0 || queue.length > 0 || pendingRetries > 0;
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
  // Anything already running belongs to the session being ended: moving the
  // generation is how a producer is told its result is no longer wanted, so it
  // is dropped rather than written into a draft that has been replaced — or,
  // when the editor is closing, into one that is gone.
  contextGeneration += 1;
  currentReportId = reportId;
  statuses = new Map();
  overlay = new Map();
  queue = [];
  queued = new Set();
  requeue = new Set();
  retried = new Map();
  pendingRetries = 0;
  blankSince = new Map();
  forceRedraw = new Set();
  // In-flight bookkeeping too. A producer already awaiting cannot be recalled,
  // but its result is abandoned by the generation bump above — so counting it
  // as running afterwards makes isBusy() report the PREVIOUS session's work.
  // The wizard gates autosave on that, so a new report's first save waited on a
  // closed report's renders.
  running = new Set();
  active = 0;
  // Whichever slide the last session was on is not this one's.
  focused = "";
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
  // Counted per (slide, FINGERPRINT), not per slide. Design, the deck grid and
  // the thumbnails all watch the same slide and do not necessarily compute the
  // same fingerprint, so a hit from one used to clear the count another was
  // accumulating: the bound never tripped, the slide was queued again on every
  // render, and the result was a UI that flickered and a slide stuck for ever
  // on "Rendering preview".
  const seen = `${slideId}|${fingerprint}`;
  if (hasImage) {
    blankSince.delete(seen);
    return;
  }
  // From here the screen is blank and says so. Whether that is because nothing
  // was ever asked for, because a render failed and was given up on, because
  // the picture went into a key nothing reads, or because the cache entry left
  // — the answer is the same, and none of those need to be told apart to give
  // it. What must not happen is what happened: nothing.
  if (queued.has(slideId) || running.has(slideId)) return;  // already being made
  const attempts = blankSince.get(seen) ?? 0;
  if (attempts >= BLANK_ATTEMPTS) {
    // Asked for often enough. Stop, and say so where the author will see it —
    // a slide that cannot be drawn is a fact they can act on; a slide that is
    // silently empty for ever is the fault being reported.
    if (statusOf(slideId).chart !== "failed") {
      setStatus(slideId, "chart", "failed", fingerprint,
                new Error("This slide's picture could not be produced. "
                          + "Reopening the report tries again."));
      notify();
    }
    return;
  }
  blankSince.set(seen, attempts + 1);
  say("blank-on-screen", {
    slideId,
    detail: `nothing queued and no picture; attempt ${attempts + 1}`,
  });
  forceRedraw.add(slideId);
  enqueue(slideId);
}

/** Draw this slide again, now, whatever anyone believes about it.
 *
 *  The author's own override — the button offered beside a slide that will not
 *  draw. It exists because every automatic guarantee here is bounded, and has to
 *  be: a slide that cannot be drawn must stop asking for the render host rather
 *  than occupy it for ever. When the reason has been dealt with — the service is
 *  back, the template is fixed — the bound is exactly what stands in the way, so
 *  it is lifted on request rather than waited out.
 *
 *  Deliberately not limited to a slide in a failed state. The fault this was
 *  built for shows nothing wrong at all: a blank slide the queue believes is
 *  finished. A button that only worked when something was marked broken would
 *  be missing precisely then.
 */
export function redraw(slideId: string) {
  say("redraw", { slideId, detail: "asked for by the author" });
  // Everything that would otherwise decline to do the work: the count of times
  // the screen has reported this slide blank, the retries already spent on each
  // producer, and any failed status standing against it.
  for (const key of [...blankSince.keys()]) {
    if (key.startsWith(`${slideId}|`)) blankSince.delete(key);
  }
  for (const key of [...retried.keys()]) {
    if (key.startsWith(`${slideId}|`)) retried.delete(key);
  }
  const forSlide = statuses.get(slideId);
  if (forSlide) {
    for (const [id, entry] of forSlide) {
      if (entry.status === "failed") setStatus(slideId, id, "pending", null);
    }
  }
  forceRedraw.add(slideId);
  enqueue(slideId);
  notify();
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
    // The QUEUE, in the order it will be worked through — not the `queued` set,
    // which is a membership test that happens to iterate in insertion order.
    // The two agreed while everything joined at the back; the focused slide
    // joins at the front, and then the set says the wrong thing about the one
    // question this snapshot exists to answer: what runs next.
    queued: [...queue],
    running: [...running],
    focused,
    requeue: [...requeue],
    active,
    concurrency,
    renderConcurrency,
    rendersActive,
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

function needed(p: Producer, base: Omit<ProducerCtx, "fingerprint">,
                force = false): ProducerCtx | null {
  // Does this producer have work on this KIND of slide at all? Asked before
  // `force`, and it is the one thing force must not override: a special slide
  // has no question, so asking for its headline can only fail — twice per
  // forced pass, once for the title and once for the bullets.
  if (p.applies && !p.applies(base)) return null;
  const fingerprint = p.fingerprint(base);
  const c: ProducerCtx = { ...base, fingerprint, force };
  // `force` is the screen contradicting the bookkeeping: a component is showing
  // this slide and has no picture for it. That is a statement about the
  // PICTURE, so it is passed to the producers and the one that owns the picture
  // acts on it (its cache does not get to answer under force).
  //
  // It used to short-circuit here, for every producer. But "already stored" is
  // where the rules that protect the AUTHOR live — never regenerate over a
  // headline somebody typed, never rewrite themes they edited by hand — and
  // force is not only the button: the queue sets it itself whenever the screen
  // reports a slide blank, which happens when an image is evicted from the
  // cache and scrolls back into view. Their words were being replaced by a
  // model with nobody clicking anything.
  const stored = p.storedFingerprint(c);
  return stored === null || stored !== fingerprint ? c : null;
}

// ── The one function ─────────────────────────────────────────────────────────

async function producePreview(slideId: string): Promise<void> {
  /** Consumed here, not at the end: the tail re-check must judge this slide by
   *  the ordinary rules, or a forced pass would find itself needed again and
   *  queue itself for ever. */
  const force = forceRedraw.delete(slideId);
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
    const c = needed(p, { slideId, chart, ctx: renderContext }, force);
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
      const patch = p.cpuBound
        ? await withRenderSlot(() => p.run(c))
        : await p.run(c);
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
      const made = retried.get(attempt) ?? 0;
      // A failure that may pass is waited out; one that says the request itself
      // is wrong gets the single retry it always had.
      const allowed = isTransient(e) ? RETRY_BACKOFF_MS.length : 1;
      if (made < allowed) {
        retried.set(attempt, made + 1);
        const delay = isTransient(e)
          ? RETRY_BACKOFF_MS[Math.min(made, RETRY_BACKOFF_MS.length - 1)]
          : 0;
        say("retry", {
          slideId,
          producer: p.id,
          detail: `attempt ${made + 1} of ${allowed}, in ${delay}ms`,
        });
        setStatus(slideId, p.id, "pending", null);
        if (delay > 0) {
          // Held as outstanding work across the wait, so nothing concludes the
          // deck is finished while a slide is between attempts.
          pendingRetries += 1;
          setTimeout(() => {
            pendingRetries -= 1;
            if (currentReportId) enqueue(slideId);
            pump();
          }, delay);
        } else {
          requeueAfterRun(slideId, "one retry after a failure");
        }
        // A producer that fails soft does not stop the slide — a headline
        // nobody could write must not also cost the slide its picture for this
        // pass. Only an "abort" producer ends it, which is what that flag
        // means; the retry itself is carried by the requeue either way.
        if (p.onFailure === "abort") return;
        continue;
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
  // Nothing comes back when there is no report open. Work abandoned because
  // the CONTEXT moved should be redone under the new one; work abandoned
  // because the editor closed should simply stop — otherwise closing a report
  // mid-render put every unfinished slide straight back on the queue, and the
  // queue went on rendering a deck nobody was looking at.
  if (!currentReportId) {
    say("dropped", { slideId, detail: "no report open" });
    return;
  }
  requeue.add(slideId);
  say("requeue-after-run", { slideId, detail: why });
}

export function enqueue(slideId: string) {
  // Nothing runs when no report is open. `requeueAfterRun` already refused, but
  // this door was left open: renaming a question or editing word merges from
  // the CASE page calls restartDeck, which enqueued every slide of the report
  // last closed — an AI title call and a full render per slide, posted into an
  // unmounted component.
  if (!currentReportId) return;
  if (!slideId || queued.has(slideId) || running.has(slideId)) return;
  // Nothing to do? Then do not join the queue, and above all do not say you
  // are working.
  //
  // The wizard offers a slide back whenever its content changes, and the
  // commonest such change is this queue's OWN generated headline arriving in
  // the draft a moment after it was written. That slide is finished. Queueing
  // it anyway was cheap in work — the pass skips every producer — but it is
  // not cheap in what the author SEES: `enqueue` marked all three producers
  // pending, the Design pane reads pending as "Updating…", and with one render
  // at a time on a deck still drawing, that badge sat over a finished slide
  // until its turn came round to discover it had nothing to do.
  //
  // Asked as one question — is ANY producer needed — rather than per producer.
  // The producers run in order and feed each other: a slide with no headline
  // yet has an image fingerprint that will MOVE once the headline is written,
  // so "the image is up to date" is only true here if nothing before it is
  // going to run. Any needed, all pending; none needed, no queue at all.
  const chart = readSlide(slideId);
  if (chart && PRODUCERS.length && !forceRedraw.has(slideId)
      && !PRODUCERS.some((p) => needed(p, { slideId, chart, ctx: renderContext }))) {
    say("nothing-to-do", { slideId });
    return;
  }
  queued.add(slideId);
  // The slide being looked at goes first, however it came to be queued — an
  // edit, a retry, a deck-wide restart. Everything else joins the back.
  if (slideId === focused) queue.unshift(slideId);
  else queue.push(slideId);
  say("enqueue", { slideId, detail: slideId === focused ? "focused; to the head" : undefined });
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

/** How many slides the renderer can usefully draw at once.
 *
 *  Told by the server, which knows its own core count; see `/health`. Raising
 *  it starts more work immediately, so a late answer costs nothing.
 */
/** How many pictures the render host can usefully draw at once.
 *
 *  Told by the server, which knows its own core count; see `/health`. It bounds
 *  the DRAWING only — slide passes go on overlapping, so thirty headlines are
 *  still written in parallel while one picture at a time is drawn. Raising it
 *  lets waiting work start immediately, so a late answer costs nothing.
 */
export function setRenderConcurrency(n: number) {
  const next = Math.max(1, Math.floor(n) || 1);
  if (next === renderConcurrency) return;
  say("render-concurrency", { detail: `${renderConcurrency} -> ${next}` });
  renderConcurrency = next;
  // Anything already waiting for a slot may now have one.
  for (let i = rendersActive; i < renderConcurrency; i += 1) renderWaiters.shift()?.();
  pump();
}

/** The author is looking at this slide.
 *
 *  Remembered, so that everything queued for it from now on goes to the head —
 *  not just the work outstanding at the moment they selected it. `promote` is
 *  the weaker signal underneath ("this one, now"), and is still what a
 *  thumbnail scrolling into view uses.
 */
export function setFocused(slideId: string) {
  if (focused === slideId) return;
  focused = slideId;
  say("focus", { slideId });
  promote(slideId);
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
  while (queue.length) {
    // The slide the author is looking at gets a slot of its own, over and above
    // the background fan-out.
    //
    // Promoting it to the head was not enough. The head still had to wait for
    // one of the background passes to end, and a pass is mostly a model writing
    // a headline — seconds — so the wait grew with the fan-out that was meant to
    // make things faster: measured on a cold 30-slide deck, clicking a slide
    // cost 6.0s with one pass, 9.8s with four, 19.8s with eight. Faster deck,
    // slower slide, and the slide is the part anybody notices.
    //
    // Bounded to one extra by the running set: once it has started, the slide is
    // running, so the next turn of this loop grants nothing.
    const first = queue[0];
    const jumpsTheQueue = first === focused && !running.has(first);
    if (active >= concurrency && !jumpsTheQueue) break;
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
  retried = new Map();
  pendingRetries = 0;
  blankSince = new Map();
  forceRedraw = new Set();
  active = 0;
  focused = "";
  contextGeneration = 0;
  trace = [];
  concurrency = 1;
  renderConcurrency = 1;
  rendersActive = 0;
  renderWaiters = [];
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
      passes: (n: number) => string;
      renders: (n: number) => string;
      debug: (on?: boolean) => string;
      redraw: (slideId: string) => void;
    };
  }
}

if (typeof window !== "undefined") {
  window.__previewQueue = {
    state: snapshot,
    trace: getTrace,
    // The same thing the button does, for a slide you can name but cannot
    // click — and for asking someone on a call to try it without walking them
    // to the right pane first.
    redraw,
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
    // The two limits, settable live. Diagnosing "the first open is slow" means
    // comparing settings on the SAME cold deck, and rebuilding the app between
    // each one changes more than the setting.
    passes: (n: number) => {
      concurrency = Math.max(1, Math.floor(n) || 1);
      pump();
      return `slide passes: ${concurrency}`;
    },
    renders: (n: number) => {
      setRenderConcurrency(n);
      return `render slots: ${renderConcurrency}`;
    },
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
