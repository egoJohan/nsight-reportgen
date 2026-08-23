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
  onFailure: "continue" | "abort";
}

// ── The seams to the wizard ──────────────────────────────────────────────────
// Registered on mount. The queue never imports React, and the wizard never
// reaches into the queue's internals.

type SlideSource = (slideId: string) => ChartSpec | null;
type PatchSink = (slideId: string, patch: Partial<ChartSpec>) => void;

let slideSource: SlideSource = () => null;
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
export function setPatchSink(fn: PatchSink) {
  patchSink = fn;
}
export function setRenderContext(ctx: RenderContext) {
  renderContext = ctx;
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

/** Start over for a different report. Statuses are per report — reading one
 *  report's as another's would show finished work that was never done. */
export function reset(reportId: string) {
  if (reportId === currentReportId) return;
  currentReportId = reportId;
  statuses = new Map();
  overlay = new Map();
  queue = [];
  queued = new Set();
  notify();
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

  for (const p of PRODUCERS) {
    const chart = readSlide(slideId);
    if (!chart) return; // deleted while queued
    const c = needed(p, { slideId, chart, ctx: renderContext });
    if (!c) continue;
    handled.set(p.id, c.fingerprint);
    setStatus(slideId, p.id, "running", c.fingerprint);
    try {
      const patch = await p.run(c);
      if (patch) applyPatch(slideId, patch);
      // The fingerprint captured BEFORE the run, never one re-read after it:
      // re-reading would record work that was never done.
      setStatus(slideId, p.id, "done", c.fingerprint);
    } catch (e) {
      setStatus(slideId, p.id, "failed", c.fingerprint, e);
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
  if (moved) enqueue(slideId);
}

// ── The queue ────────────────────────────────────────────────────────────────

export function enqueue(slideId: string) {
  if (!slideId || queued.has(slideId) || running.has(slideId)) return;
  queued.add(slideId);
  queue.push(slideId);
  pump();
}

/** The slide the author just selected renders next. */
export function promote(slideId: string) {
  const i = queue.indexOf(slideId);
  if (i > 0) {
    queue.splice(i, 1);
    queue.unshift(slideId);
  }
  pump();
}

function pump() {
  while (active < concurrency && queue.length) {
    const slideId = queue.shift()!;
    queued.delete(slideId);
    running.add(slideId);
    active += 1;
    notify();
    void producePreview(slideId).finally(() => {
      running.delete(slideId);
      active -= 1;
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
export function __resetForTest() {
  currentReportId = "";
  statuses = new Map();
  overlay = new Map();
  queue = [];
  queued = new Set();
  running = new Set();
  active = 0;
  concurrency = 4;
  PRODUCERS = [];
}

export { imageFingerprint };
