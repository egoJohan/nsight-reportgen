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

export interface Question {
  qid: string;
  kind: "single" | "multi";
  variables: string[];
  text: string;
  suggested_chart_type: string;
  missing_values: MissingValue[];
}

export interface Variable {
  name: string;
  label: string;
  measurement: string;
}

export interface UploadResult {
  material_id: string;
  question_count: number;
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
  slide_title: string | null;
  slide_description: string | null;
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
  },

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

    previewChart: async (
      materialId: string,
      chart: ChartSpec
    ): Promise<Blob> => {
      const res = await fetch(
        `${API_BASE}/materials/${materialId}/preview-chart`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(chart),
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
  },
};
