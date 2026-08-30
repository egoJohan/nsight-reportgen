/**
 * The producers: what a slide preview is made of.
 *
 * One entry per kind of work. Each says what its output depends on (a
 * fingerprint), what the existing output was made for (a stored fingerprint),
 * and how to make it. The queue runs them in this order, per slide, in one
 * sequential function.
 *
 * Adding a future kind of work — a generated commentary, an alt-text, a
 * per-slide summary — is one more entry here, and nothing else changes. "Shorten
 * with AI" is deliberately NOT here: it is a button the author presses, not
 * automatic work, and it stays that way until someone decides otherwise.
 */
import { api, type ChartSpec, type GroupingOverride, type Question } from "./api";
import { isSpecialSlide, isThemes, titleDataKey } from "./charts";
import { imageFingerprint } from "./previewFingerprint";
import { setProducers, type Producer, type ProducerCtx } from "./previewQueue";

/** What the producers need from the wizard that is not on the chart itself. */
export interface ProducerEnv {
  materialId: string;
  /** The question as the CURRENT grouping resolves it — the title is written
   *  about that text, not about the raw variable. */
  questionFor: (questionRef: string) => Question | undefined;
  grouping: () => GroupingOverride | undefined;
  /** Is this image already in the client cache? */
  hasImage: (fingerprint: string) => boolean;
  /** Fetch it and put it there.
   *
   *  Takes the render context the QUEUE ran with — not one captured in a
   *  closure. A template change refills the queue synchronously, starting work
   *  before the new closure is installed, so a closure-held context names the
   *  PREVIOUS template: the picture came back drawn on it and was stored under
   *  the new template's fingerprint. Every slide was rendered, every count was
   *  right, and the deck stayed on the old template. */
  fetchImage: (
    chart: ChartSpec,
    fingerprint: string,
    ctx: { templateRef: string; reportId: string }
  ) => Promise<void>;
}

let env: ProducerEnv | null = null;

export function setProducerEnv(next: ProducerEnv) {
  env = next;
}

const title: Producer = {
  id: "title",

  fingerprint: (c) => titleDataKey(c.chart, env?.questionFor(c.chart.question_ref)),

  storedFingerprint: (c: ProducerCtx) => {
    // Special slides carry bullets, not a generated headline.
    if (isSpecialSlide(c.chart)) return c.fingerprint;
    // The grouping has not resolved this question yet. Claim "nothing to do"
    // rather than run: a run that produced nothing would be recorded as DONE at
    // this fingerprint and never retried, which left four slides of a sixty
    // slide report permanently untitled. Once the question resolves,
    // titleDataKey moves — it includes the resolved text — and this slide is
    // needed again on its own.
    if (!env?.questionFor(c.chart.question_ref)) return c.fingerprint;
    // Written for a known set of data: valid until that data moves.
    if (c.chart.slide_title_key) return c.chart.slide_title_key;
    // A title with no key was typed by a person (SlideTitleField clears the key
    // on every keystroke). Never regenerate over someone's own words: claiming
    // it is already up to date is how that is expressed here.
    if (c.chart.slide_title) return c.fingerprint;
    // Nothing yet.
    return null;
  },

  run: async (c) => {
    if (!env) return;
    const { title: text } = await api.materials.aiSlideTitle(env.materialId, {
      question_ref: c.chart.question_ref,
      statistic: c.chart.statistic,
      classifying_var: c.chart.classifying_var,
      show_not_answered: c.chart.show_not_answered,
      not_answered_codes: c.chart.not_answered_codes,
      grouping: env.grouping(),
    });
    if (!text) return;
    // Tagged with the data it was written about, so a template swap, a re-sort
    // or a recolour never regenerates it — only a change to the data does.
    return { slide_title: text, slide_title_key: c.fingerprint };
  },

  // The request is a round trip to a model — seconds, not milliseconds — and an
  // author looking at an untitled slide types a headline into exactly that gap.
  // Theirs stands. A typed title is one with no key: SlideTitleField clears the
  // key on every keystroke, which is the same signal storedFingerprint reads.
  supersededBy: (before, after) =>
    (after.slide_title ?? "") !== (before.slide_title ?? "") && !after.slide_title_key,

  // A headline nobody could write does not stop the slide being drawn: it falls
  // back to the question text, which is what happened before AI titles existed.
  onFailure: "continue",
};

const bullets: Producer = {
  id: "bullets",

  fingerprint: (c) => c.chart.question_ref,

  storedFingerprint: (c: ProducerCtx) => {
    if (!isThemes(c.chart)) return c.fingerprint; // not this slide's kind of work
    const existing = (c.chart.options?.bullets as string[] | undefined)?.length;
    // Generate-once, as before: themes are expensive and an author who edits
    // them should not have them rewritten underneath.
    return existing ? c.fingerprint : null;
  },

  run: async (c) => {
    if (!env) return;
    const { bullets: made } = await api.materials.aiThemes(env.materialId, {
      question_ref: c.chart.question_ref,
    });
    if (!made?.length) return;
    return { options: { ...(c.chart.options ?? {}), bullets: made } };
  },

  onFailure: "continue",
};

const chart: Producer = {
  id: "chart",

  fingerprint: (c) => imageFingerprint(c.chart, c.ctx),

  // The client cache IS the record of what has been rendered, so an evicted
  // image is simply missing and gets made again.
  storedFingerprint: (c: ProducerCtx) =>
    env?.hasImage(c.fingerprint) ? c.fingerprint : null,

  run: async (c) => {
    // Not "nothing to do": recording a render that never happened would leave
    // the slide blank with no way back. Failing marks it retryable instead.
    if (!env) throw new Error("preview producers used before setProducerEnv");
    await env.fetchImage(c.chart, c.fingerprint, {
      templateRef: c.ctx.templateRef,
      reportId: c.ctx.reportId,
    });
  },

  // This is the render host's CPU — LibreOffice, PDF, raster — so the queue
  // holds it to the number of cores that host reports. The title and bullets
  // producers above are the opposite: a round trip to a model, spent waiting,
  // costing that host nothing, and free to overlap across slides.
  cpuBound: true,

  // Nothing downstream should pretend an image exists.
  onFailure: "abort",
};

/** Title, then bullets, then the image — the image fingerprint covers the
 *  title, so drawing last is what makes a late headline cost one render rather
 *  than two. */
export function installProducers() {
  setProducers([title, bullets, chart]);
}

export const __producersForTest = { title, bullets, chart };
