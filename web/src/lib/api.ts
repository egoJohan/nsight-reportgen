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
  kind: "single" | "multi";
  variables: string[];
  text: string;
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
}

export interface Variable {
  name: string;
  label: string;
  measurement: string;
}

// ---- Question details (computed summary) ----
export interface QuestionDistRow {
  category: string;
  count: number | null;
  pct: number | null;
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
  basis: "data_order" | "pct" | "topbox_sum" | "mean" | "count";
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
}

// ---- Client ----

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// The backend renders previews through LibreOffice, which is now concurrency-safe
// (a small pool of isolated profiles). Run previews through a bounded pool so a
// grid of thumbnails generates in PARALLEL — but capped, to match the backend's
// soffice pool and avoid overwhelming it. Cached previews resolve instantly and
// don't occupy a slot for long.
const PREVIEW_CONCURRENCY = 4;
let previewActive = 0;
const previewQueue: Array<() => void> = [];

function serializePreview<T>(task: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const start = () => {
      previewActive++;
      task().then(resolve, reject).finally(() => {
        previewActive--;
        const next = previewQueue.shift();
        if (next) next();
      });
    };
    if (previewActive < PREVIEW_CONCURRENCY) start();
    else previewQueue.push(start);
  });
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

    variables: (materialId: string): Promise<{ variables: Variable[] }> =>
      fetch(`${API_BASE}/materials/${materialId}/variables`).then((r) =>
        json<{ variables: Variable[] }>(r)
      ),

    questionSummary: (materialId: string, qid: string): Promise<QuestionSummary> =>
      fetch(`${API_BASE}/materials/${materialId}/questions/${qid}/summary`).then(
        (r) => json<QuestionSummary>(r)
      ),

    previewChart: (
      materialId: string,
      chart: ChartSpec,
      opts?: { renderTitle?: boolean }
    ): Promise<Blob> =>
      serializePreview(async () => {
        // When renderTitle is false the PNG omits the baked title block, so the
        // frontend owns the title region (progressive preview overlay).
        const body =
          opts?.renderTitle === undefined
            ? chart
            : { ...chart, render_title: opts.renderTitle };
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
      }),

    // AI: generate a descriptive slide title. May 503 if egoHive is down —
    // surfaces the backend {detail} message.
    aiSlideTitle: async (
      materialId: string,
      body: AiSlideTitleBody
    ): Promise<{ title: string }> => {
      const res = await fetch(
        `${API_BASE}/materials/${materialId}/ai/slide-title`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      );
      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const b = await res.json();
          if (b && typeof b.detail === "string") detail = b.detail;
        } catch {
          // not JSON
        }
        throw new Error(detail);
      }
      return res.json() as Promise<{ title: string }>;
    },

    // AI: shorten category labels into [full, short] pairs. May return pairs
    // equal to the originals when egoHive is unavailable (graceful), or 503.
    aiShortLabels: async (
      materialId: string,
      body: AiShortLabelsBody
    ): Promise<{ overrides: [string, string][] }> => {
      const res = await fetch(
        `${API_BASE}/materials/${materialId}/ai/short-labels`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      );
      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const b = await res.json();
          if (b && typeof b.detail === "string") detail = b.detail;
        } catch {
          // not JSON
        }
        throw new Error(detail);
      }
      return res.json() as Promise<{ overrides: [string, string][] }>;
    },
  },

  reports: {
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
      view: "slides" = "slides"
    ): Promise<{ pdf_url: string }> => {
      const res = await fetch(
        `${API_BASE}/cases/${caseId}/reports/${reportId}/render`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ material_id: materialId, view }),
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
