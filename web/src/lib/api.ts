const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8200";

// ---- Types ----

export interface Case {
  id: string;
  name: string;
}

export interface MissingValue {
  code: number;
  label: string;
}

export interface ValueLabel {
  code: number;
  label: string;
}

export interface Question {
  qid: string;
  kind: "single" | "multi" | "battery" | "comparison";
  variables: string[];
  text: string;
  // Member qids for a comparison (overlaid parallel questions); [] otherwise.
  members?: string[];
  // Whether the question can be charted at all (false for open-ended text).
  chartable: boolean;
  // Human-readable reason when chartable === false (e.g. "Open-ended text answers").
  non_chartable_reason: string | null;
  suggested_chart_type: string;
  // Chart-type ids whose plugin suitability applies to this question.
  compatible_chart_types: string[];
  missing_values: MissingValue[];
  // All value labels incl. missing (single questions); [] for multi.
  values: ValueLabel[];
  // Base category label strings, in render order — the label-editor's list.
  category_labels: string[];
  // Respondent-background question (age/gender/region/…) — floated to the front
  // of a new report (demographics-first convention).
  is_demographic?: boolean;
}

export interface Variable {
  name: string;
  label: string;
  measurement: string;
  n_values?: number;
  // Whether a per-category mean is meaningful (numeric/rating) — a valid combo
  // secondary variable.
  aggregatable?: boolean;
  // Whether this is a meaningful classifying/segmentation variable (background/
  // demographic categorical, not a Likert item) — drives the classifier picker.
  segmentable?: boolean;
  // A genuine multi-response tick-box (binary 0/1) — the only kind groupable
  // into a multi-response question.
  tickbox?: boolean;
  // A rating scale (digit- or word-labelled 1..N) — groupable into a battery.
  scale?: boolean;
  // Signature of the scale; two variables can form a battery only if these match.
  scale_key?: string | null;
  // Looser signature — the scale's POINT set (1..N). Variables sharing this are
  // battery-COMPATIBLE even when worded differently (drives 'Group as battery').
  scale_compat_key?: string | null;
}

// A word-cloud value merge: variant tokens (`words`, lowercased) folded into one
// displayed word (`label`), summing their counts.
export interface WordMerge {
  label: string;
  words: string[];
}

// ---- Question details (computed summary) ----
export interface QuestionDistRow {
  category: string;
  count: number | null;
  pct: number | null;
  mean?: number | null;
}

export interface QuestionSummary {
  qid: string;
  kind: string;
  text: string;
  measurement: string;
  variables: { name: string; label: string; measurement: string }[];
  value_labels: ValueLabel[];
  missing_values: MissingValue[];
  category_labels: string[];
  chartable: boolean;
  non_chartable_reason: string | null;
  respondent_total: number;
  base_n: number | null;
  statistic: string;
  distribution: QuestionDistRow[] | null;
  mean: number | null;
  suggested_chart_type?: string;
  compatible_chart_types?: string[];
}

export interface UploadResult {
  material_id: string;
  question_count: number;
  // The SAV's embedded study title, if any (null otherwise).
  file_label?: string | null;
}

// ---- Report / ChartSpec ----

export interface NumberFormat {
  mode: "auto" | "manual";
  pct_decimals: number;
  mean_decimals: number;
  count_round_up: boolean;
  show_pct_sign: boolean;
}

export interface SortSpec {
  basis: "data_order" | "pct" | "topbox_sum" | "top3_sum" | "mean" | "count";
  topbox_codes: number[];
  descending: boolean;
}

export interface ChartElements {
  title: boolean;
  legend: boolean;
  n: boolean;
  axis_names: boolean;
  filter_var: boolean;
  data_labels: boolean;
}

export interface ChartSpec {
  question_ref: string;
  chart_type: string;
  statistic: "pct" | "count" | "mean" | "median" | "sum";
  classifying_var: string | null;
  classifying_var_2?: string | null;  // secondary classifier → cross-tab combos
  number_format: NumberFormat;
  sort: SortSpec;
  template_slot: string;
  elements: ChartElements;
  scatter_xy: [string, string] | null;
  show_not_answered: boolean;
  // When false, categories that are 0% across all segments are dropped.
  show_empty_categories: boolean;
  // null = use SAV-detected missing set; an explicit list overrides it.
  not_answered_codes: number[] | null;
  // Ordered [full_label, short_label] display overrides.
  category_label_overrides: [string, string][];
  slide_title: string | null;
  slide_description: string | null;
  // Override the methodology footer (e.g. a simpler "N = 950"); null = auto
  // ("<stat> · n = N"). "{n}" expands to the base count, "{stat}" to the stat label.
  footer_note: string | null;
  // Cross-tab percentage direction: "auto" (resolve from variable roles),
  // "classifier" (within each segment), "question" (within each base category),
  // "total" (over the grand total).
  percent_base?: "auto" | "classifier" | "question" | "total";
  // Free-form per-chart-type options (plugin-declared config keys without a
  // first-class ChartSpec field). Optional for backward compatibility.
  options?: Record<string, unknown>;
}

// ---- Chart-type catalog (plugin-declared config schema) ----
export interface ConfigFieldOption {
  value: string;
  label: string;
}

export interface ConfigField {
  key: string;
  widget: string; // select | switch | number | variable | sort | number_format | not_answered | category_labels | scatter_xy | note
  label: string;
  help?: string;
  options?: ConfigFieldOption[];
  default?: unknown;
  required?: boolean;
}

export interface ChartTypeInfo {
  id: string;
  label: string;
  requires: string[];
  config: ConfigField[];
}

// ---- AI text generation ----

export interface AiSlideTitleBody {
  question_ref: string;
  statistic?: string;
  classifying_var?: string | null;
  number_format?: NumberFormat;
  show_not_answered?: boolean;
  not_answered_codes?: number[] | null;
  // The report's grouping, so a title for a grouped question (battery/multi) resolves.
  grouping?: GroupingOverride;
}

export interface AiShortLabelsBody {
  question_ref?: string;
  categories?: string[];
}

export interface ReportDoc {
  name: string;
  render_mode: "image";
  template_ref: string;
  charts: ChartSpec[];
  grouping?: GroupingOverride;
}

// ---- Client ----

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// All egoHive-backed AI calls (titles, short-labels, special slides) share one
// bounded concurrency gate so the title auto-batch + special-slide generation
// never collectively overload egoHive (which returns 503 under load). Transient
// 503s are retried with backoff. egoHive tolerates ~2 concurrent comfortably.
const AI_CONCURRENCY = 2;
let aiActive = 0;
const aiQueue: Array<() => void> = [];

function aiGate<T>(task: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const start = () => {
      aiActive++;
      task()
        .then(resolve, reject)
        .finally(() => {
          aiActive--;
          aiQueue.shift()?.();
        });
    };
    if (aiActive < AI_CONCURRENCY) start();
    else aiQueue.push(start);
  });
}

const _sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// POST an AI request through the gate, retrying transient 503s with backoff.
// Non-503 errors are terminal. Surfaces the backend {detail} on failure.
async function aiPost<T>(path: string, body: unknown): Promise<T> {
  return aiGate(async () => {
    const backoffs = [0, 700, 1800]; // attempt 1 immediate, then back off
    let lastDetail = "AI request failed";
    for (let attempt = 0; attempt < backoffs.length; attempt++) {
      if (backoffs[attempt]) await _sleep(backoffs[attempt]);
      const res = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) return res.json() as Promise<T>;
      let detail = `${res.status} ${res.statusText}`;
      try {
        const b = await res.json();
        if (b && typeof b.detail === "string") detail = b.detail;
      } catch {
        // not JSON
      }
      lastDetail = detail;
      if (res.status !== 503) throw new Error(detail); // only 503 is retryable
    }
    throw new Error(lastDetail);
  });
}

// POST a special-slide AI request (overview/conclusion/demographics).
function postAi<T>(materialId: string, kind: string, body: unknown): Promise<T> {
  return aiPost<T>(`/materials/${materialId}/ai/${kind}`, body);
}

// The backend renders previews through LibreOffice (a small pool of isolated
// profiles). Run previews through a bounded, KEY-AWARE pool so the deck warms in
// the background — but the slide the user is LOOKING AT is never stuck behind it.
//
// Why key-aware: React Query dedupes by query key, so the active slide and the
// background deck-prefetch share ONE request. A boolean "priority" on the request
// can't help — whichever observer created it first (usually the background
// prefetch) decides its lane. Instead the active slide announces its KEY via
// setActivePreviewKey(); the gate then PROMOTES whichever queued task matches
// that key, running it immediately in a reserved slot. So selecting a not-yet-
// rendered slide from the end of the deck renders it right away.
const PREVIEW_CONCURRENCY = 4;
const PRIORITY_RESERVE = 1; // slot kept free so the active slide can always start
let previewActive = 0;
let activePreviewKey: string | null = null;
const previewQueue: Array<{ start: () => void; key: string }> = [];

// The slide the user is currently viewing (its render-content key). Its queued
// render jumps the queue. Called by useChartPreview for the active preview.
export function setActivePreviewKey(key: string | null) {
  activePreviewKey = key;
  pumpPreview();
}

function pumpPreview() {
  // 1) The active slide's queued render runs first and may use the reserved slot.
  if (activePreviewKey) {
    let i: number;
    while (
      previewActive < PREVIEW_CONCURRENCY &&
      (i = previewQueue.findIndex((q) => q.key === activePreviewKey)) !== -1
    ) {
      previewActive++;
      previewQueue.splice(i, 1)[0].start();
    }
  }
  // 2) Background renders fill the rest, but stay below the pool size so the
  //    reserved slot is always free for a freshly-selected slide.
  while (
    previewQueue.length &&
    previewActive < PREVIEW_CONCURRENCY - PRIORITY_RESERVE
  ) {
    previewActive++;
    previewQueue.shift()!.start();
  }
}

function serializePreview<T>(task: () => Promise<T>, key = ""): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const start = () => {
      task().then(resolve, reject).finally(() => {
        previewActive--;
        pumpPreview();
      });
    };
    previewQueue.push({ start, key });
    pumpPreview();
  });
}

export interface GroupSpec {
  kind: "multi" | "battery";
  variables: string[];
  label?: string | null;
}

// A Tier-2 comparison: overlay these parallel questions (by qid) as multi-series.
// The chart type (radar / grouped bar) is chosen in the Design phase, not stored here.
export interface ComparisonSpec {
  members: string[];
  label?: string | null;
}

export interface GroupingOverride {
  groups: GroupSpec[];
  singles: string[];
  comparisons?: ComparisonSpec[];
}

// A confirmable hint: a run of ≥3 contiguous same-scale variables that could be a
// battery (stacked comparison). Surfaced by /regroup; never applied automatically.
export interface BatterySuggestion {
  variables: string[];
  labels: string[];
}

// Parallel questions sharing a category set — seeds the comparison suggestions.
export interface ParallelSuggestion {
  kind: "multi" | "battery";
  qids: string[];
  labels: string[];
}

export interface CaseMaterial {
  material_id: string;
  name: string;
}

export interface CaseReportInfo {
  report_id: string;
  name: string;
}

export const api = {
  cases: {
    list: (): Promise<Case[]> =>
      fetch(`${API_BASE}/cases`).then((r) => json<Case[]>(r)),

    create: (name: string): Promise<{ case_id: string }> =>
      fetch(`${API_BASE}/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }).then((r) => json<{ case_id: string }>(r)),

    rename: (caseId: string, name: string): Promise<{ id: string; name: string }> =>
      fetch(`${API_BASE}/cases/${caseId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }).then((r) => json<{ id: string; name: string }>(r)),

    remove: (caseId: string): Promise<{ deleted: string }> =>
      fetch(`${API_BASE}/cases/${caseId}`, { method: "DELETE" }).then((r) =>
        json<{ deleted: string }>(r)
      ),
  },

  // Plugin-declared chart-type catalog + config schema (material-independent).
  chartTypes: (): Promise<{ chart_types: ChartTypeInfo[] }> =>
    fetch(`${API_BASE}/chart-types`).then((r) =>
      json<{ chart_types: ChartTypeInfo[] }>(r)
    ),

  materials: {
    // Server-side list of a case's materials (visible to any user/device).
    listForCase: (caseId: string): Promise<{ materials: CaseMaterial[] }> =>
      fetch(`${API_BASE}/cases/${caseId}/materials`).then((r) =>
        json<{ materials: CaseMaterial[] }>(r)
      ),

    upload: (caseId: string, file: File): Promise<UploadResult> => {
      const form = new FormData();
      form.append("file", file);
      return fetch(`${API_BASE}/cases/${caseId}/materials`, {
        method: "POST",
        body: form,
      }).then((r) => json<UploadResult>(r));
    },

    questions: (materialId: string): Promise<{ questions: Question[] }> =>
      fetch(`${API_BASE}/materials/${materialId}/questions`).then((r) =>
        json<{ questions: Question[] }>(r)
      ),

    variables: (
      materialId: string,
      opts?: { all?: boolean }
    ): Promise<{ variables: Variable[] }> =>
      fetch(
        `${API_BASE}/materials/${materialId}/variables${opts?.all ? "?include_all=true" : ""}`
      ).then((r) => json<{ variables: Variable[] }>(r)),

    // Stateless preview: reshape the question list for a report's grouping override
    // (the override itself is saved WITH the report, not per material).
    regroup: (
      materialId: string,
      override: GroupingOverride
    ): Promise<{
      questions: Question[];
      battery_suggestions: BatterySuggestion[];
      parallel_suggestions: ParallelSuggestion[];
    }> =>
      fetch(`${API_BASE}/materials/${materialId}/regroup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(override),
      }).then((r) =>
        json<{
          questions: Question[];
          battery_suggestions: BatterySuggestion[];
          parallel_suggestions: ParallelSuggestion[];
        }>(r)
      ),

    questionSummary: (
      materialId: string,
      qid: string,
      grouping?: GroupingOverride
    ): Promise<QuestionSummary> => {
      // Pass the report grouping so a battery/multi qid resolves (else the summary 404s).
      const qs = grouping
        ? `?grouping=${encodeURIComponent(JSON.stringify(grouping))}`
        : "";
      return fetch(
        `${API_BASE}/materials/${materialId}/questions/${qid}/summary${qs}`
      ).then((r) => json<QuestionSummary>(r));
    },

    // Word-cloud editing: the question's raw top words (+ current merges) and a
    // setter to persist merges (fold token variants into one word).
    questionWords: (
      materialId: string,
      qid: string
    ): Promise<{ words: { word: string; count: number }[]; merges: WordMerge[] }> =>
      fetch(`${API_BASE}/materials/${materialId}/questions/${qid}/words`).then((r) =>
        json<{ words: { word: string; count: number }[]; merges: WordMerge[] }>(r)
      ),

    setWordMerges: (
      materialId: string,
      qid: string,
      merges: WordMerge[]
    ): Promise<{ qid: string; merges: WordMerge[] }> =>
      fetch(`${API_BASE}/materials/${materialId}/questions/${qid}/word-merges`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ merges }),
      }).then((r) => json<{ qid: string; merges: WordMerge[] }>(r)),

    // Rename a question for this material (case-page edit). Blank reverts to the
    // original SAV label. Applies to every report/chart/deck using the question.
    setQuestionLabel: (
      materialId: string,
      qid: string,
      label: string
    ): Promise<{ qid: string; label: string | null }> =>
      fetch(`${API_BASE}/materials/${materialId}/questions/${qid}/label`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label }),
      }).then((r) => json<{ qid: string; label: string | null }>(r)),

    previewChart: (
      materialId: string,
      chart: ChartSpec,
      opts?: { renderTitle?: boolean; key?: string; grouping?: GroupingOverride }
    ): Promise<Blob> =>
      serializePreview(async () => {
        // When renderTitle is false the PNG omits the baked title block, so the
        // frontend owns the title region (progressive preview overlay). The
        // report's grouping is included so a chart on a manually-grouped question
        // previews the same way it renders.
        const body: Record<string, unknown> = {
          ...chart,
          ...(opts?.renderTitle === undefined ? {} : { render_title: opts.renderTitle }),
          ...(opts?.grouping ? { grouping: opts.grouping } : {}),
        };
        const res = await fetch(
          `${API_BASE}/materials/${materialId}/preview-chart`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        );
        if (!res.ok) {
          // Backend returns {detail: "<reason>"} for 422 (and 503 etc.)
          let detail = `${res.status} ${res.statusText}`;
          try {
            const body = await res.json();
            if (body && typeof body.detail === "string") detail = body.detail;
          } catch {
            // not JSON — keep status text
          }
          throw new Error(detail);
        }
        return res.blob();
      }, opts?.key ?? ""),

    // AI: generate a descriptive slide title. Goes through the shared AI gate
    // (bounded concurrency + 503 retry); surfaces the backend {detail} message.
    aiSlideTitle: (
      materialId: string,
      body: AiSlideTitleBody
    ): Promise<{ title: string; subtitle?: string }> =>
      aiPost(`/materials/${materialId}/ai/slide-title`, body),

    // AI: shorten category labels into [full, short] pairs. Through the shared
    // AI gate (bounded concurrency + 503 retry).
    aiShortLabels: (
      materialId: string,
      body: AiShortLabelsBody
    ): Promise<{ overrides: [string, string][] }> =>
      aiPost(`/materials/${materialId}/ai/short-labels`, body),

    // AI: special-slide bullet generators. All may 503 if egoHive is down.
    aiOverview: (
      materialId: string,
      body: { question_refs?: string[] }
    ): Promise<{ bullets: string[] }> =>
      postAi(materialId, "overview", body),

    aiConclusion: (
      materialId: string,
      body: { question_refs?: string[] }
    ): Promise<{ bullets: string[] }> =>
      postAi(materialId, "conclusion", body),

    aiDemographics: (
      materialId: string,
      body: { question_refs?: string[] }
    ): Promise<{
      bullets: string[];
      question_refs: string[];
      charts: { question_ref: string; chart_type: string }[];
    }> => postAi(materialId, "demographics", body),

    // AI: summarise an open-ended question's answers into key themes (bullets).
    aiThemes: (
      materialId: string,
      body: { question_ref: string }
    ): Promise<{ bullets: string[] }> =>
      aiPost(`/materials/${materialId}/ai/themes`, body),

    // AI: chat with a data-aware assistant about this material's survey data.
    chat: (
      materialId: string,
      messages: { role: "user" | "assistant"; content: string }[]
    ): Promise<{ reply: string }> =>
      aiPost(`/materials/${materialId}/chat`, { messages }),
  },

  reports: {
    // Server-side list of a case's reports (visible to any user/device).
    listForCase: (caseId: string): Promise<{ reports: CaseReportInfo[] }> =>
      fetch(`${API_BASE}/cases/${caseId}/reports`).then((r) =>
        json<{ reports: CaseReportInfo[] }>(r)
      ),

    create: (
      caseId: string,
      report: ReportDoc
    ): Promise<{ report_id: string }> =>
      fetch(`${API_BASE}/cases/${caseId}/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(report),
      }).then((r) => json<{ report_id: string }>(r)),

    update: (
      caseId: string,
      reportId: string,
      report: ReportDoc
    ): Promise<{ report_id: string }> =>
      fetch(`${API_BASE}/cases/${caseId}/reports/${reportId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(report),
      }).then((r) => json<{ report_id: string }>(r)),

    get: (caseId: string, reportId: string): Promise<ReportDoc> =>
      fetch(`${API_BASE}/cases/${caseId}/reports/${reportId}`).then((r) =>
        json<ReportDoc>(r)
      ),

    remove: (
      caseId: string,
      reportId: string
    ): Promise<{ deleted: boolean }> =>
      fetch(`${API_BASE}/cases/${caseId}/reports/${reportId}`, {
        method: "DELETE",
      }).then((r) => json<{ deleted: boolean }>(r)),

    // Run the full PPTX → PDF → raster render chain (slow). Surfaces the
    // backend's {detail} message (422 / 503) so the UI can show the reason.
    render: async (
      caseId: string,
      reportId: string,
      materialId: string,
      view: "slides" = "slides",
      signal?: AbortSignal
    ): Promise<{ pdf_url: string }> => {
      const res = await fetch(
        `${API_BASE}/cases/${caseId}/reports/${reportId}/render`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ material_id: materialId, view }),
          signal,
        }
      );
      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          if (body && typeof body.detail === "string") detail = body.detail;
        } catch {
          // not JSON — keep status text
        }
        throw new Error(detail);
      }
      return res.json() as Promise<{ pdf_url: string }>;
    },

    previewPdf: async (caseId: string, reportId: string): Promise<Blob> => {
      const res = await fetch(
        `${API_BASE}/cases/${caseId}/reports/${reportId}/preview.pdf`
      );
      if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText}`);
      }
      return res.blob();
    },

    previewPptx: async (caseId: string, reportId: string): Promise<Blob> => {
      const res = await fetch(
        `${API_BASE}/cases/${caseId}/reports/${reportId}/preview.pptx`
      );
      if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText}`);
      }
      return res.blob();
    },
  },
};
