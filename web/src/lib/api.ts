const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8200";

// ---- Types ----

export interface Case {
  id: string;
  name: string;
}

export interface Question {
  qid: string;
  kind: "single" | "multi";
  variables: string[];
  text: string;
  suggested_chart_type: string;
  missing_values: string[];
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
  },
};
