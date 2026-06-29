import {
  useQuery,
  useMutation,
  useQueryClient,
  keepPreviousData,
} from "@tanstack/react-query";
import { api } from "./api";
import type { ChartSpec, ReportDoc } from "./api";

// ---- Query keys ----
export const qk = {
  cases: () => ["cases"] as const,
  chartTypes: () => ["chart-types"] as const,
  questions: (materialId: string) => ["questions", materialId] as const,
  variables: (materialId: string) => ["variables", materialId] as const,
  report: (caseId: string, reportId: string) =>
    ["report", caseId, reportId] as const,
};

// ---- Hooks ----

export function useCases() {
  return useQuery({ queryKey: qk.cases(), queryFn: api.cases.list });
}

export function useCreateCase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.cases.create(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.cases() }),
  });
}

export function useRenameCase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId, name }: { caseId: string; name: string }) =>
      api.cases.rename(caseId, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.cases() }),
  });
}

export function useDeleteCase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (caseId: string) => api.cases.remove(caseId),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.cases() }),
  });
}

// ---- Chart preview cache ----
// Only the fields that change the rendered PNG; identical content → identical
// cache entry → the preview is formed ONCE and reused across mounts/steps.
function previewContentKey(chart: ChartSpec, renderTitle: boolean) {
  const key: Record<string, unknown> = {
    question_ref: chart.question_ref,
    chart_type: chart.chart_type,
    statistic: chart.statistic,
    classifying_var: chart.classifying_var,
    number_format: chart.number_format,
    sort: chart.sort,
    elements: chart.elements,
    scatter_xy: chart.scatter_xy,
    show_not_answered: chart.show_not_answered,
    show_empty_categories: chart.show_empty_categories,
    not_answered_codes: chart.not_answered_codes,
    category_label_overrides: chart.category_label_overrides,
    options: chart.options ?? null,
  };
  // The title/description only affect the PNG when baked (render_title on); when
  // the frontend owns the title region, editing it must NOT re-render the chart.
  if (renderTitle) {
    key.slide_title = chart.slide_title;
    key.slide_description = chart.slide_description;
  }
  return key;
}

// Cache data URLs (plain strings), not object URLs: they are freed with the
// cache entry, so no manual revoke is needed and a cached preview survives
// component unmount/remount without reloading.
function blobToDataURL(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
}

/**
 * A cached chart preview (data URL). Keyed by material + render-affecting chart
 * fields + renderTitle, with staleTime Infinity, so the same chart never
 * re-renders: formed once, reused everywhere (Configure, Review, Slides).
 */
export function useChartPreview(
  materialId: string,
  chart: ChartSpec,
  opts?: { renderTitle?: boolean; enabled?: boolean; priority?: boolean }
) {
  const renderTitle = opts?.renderTitle ?? true;
  return useQuery({
    queryKey: ["chart-preview", materialId, renderTitle, previewContentKey(chart, renderTitle)],
    queryFn: () =>
      api.materials
        .previewChart(materialId, chart, { renderTitle, priority: opts?.priority })
        .then(blobToDataURL),
    enabled: (opts?.enabled ?? true) && !!materialId,
    staleTime: Infinity,
    gcTime: 30 * 60_000,
    retry: false,
    // Keep the previously rendered slide visible while the new render loads, so
    // editing a spec shows the old image + an "Updating…" badge instead of
    // flashing the whole-slide "Rendering preview…" placeholder.
    placeholderData: keepPreviousData,
  });
}

export function useChartTypes() {
  return useQuery({
    queryKey: qk.chartTypes(),
    queryFn: api.chartTypes,
    staleTime: Infinity, // the catalog is static for the app's lifetime
    select: (d) => d.chart_types,
  });
}

export function useQuestions(materialId: string | null) {
  return useQuery({
    queryKey: qk.questions(materialId ?? ""),
    queryFn: () => api.materials.questions(materialId!),
    enabled: !!materialId,
    select: (d) => d.questions,
  });
}

export function useQuestionSummary(materialId: string, qid: string | null) {
  return useQuery({
    queryKey: ["question-summary", materialId, qid ?? ""],
    queryFn: () => api.materials.questionSummary(materialId, qid!),
    enabled: !!materialId && !!qid,
    staleTime: 5 * 60_000,
  });
}

export function useVariables(materialId: string | null) {
  return useQuery({
    queryKey: qk.variables(materialId ?? ""),
    queryFn: () => api.materials.variables(materialId!),
    enabled: !!materialId,
    select: (d) => d.variables,
  });
}

export function useUploadMaterial(caseId: string) {
  return useMutation({
    mutationFn: (file: File) => api.materials.upload(caseId, file),
  });
}

// ---- Reports ----

export function useReport(caseId: string, reportId: string | null) {
  return useQuery({
    queryKey: qk.report(caseId, reportId ?? ""),
    queryFn: () => api.reports.get(caseId, reportId!),
    enabled: !!reportId,
  });
}

export function useCreateReport(caseId: string) {
  return useMutation({
    mutationFn: (report: ReportDoc) => api.reports.create(caseId, report),
  });
}

export function useUpdateReport(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      reportId,
      report,
    }: {
      reportId: string;
      report: ReportDoc;
    }) => api.reports.update(caseId, reportId, report),
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: qk.report(caseId, vars.reportId) }),
  });
}

export function useDeleteReport(caseId: string) {
  return useMutation({
    mutationFn: (reportId: string) => api.reports.remove(caseId, reportId),
  });
}

export function useRenderReport(caseId: string) {
  return useMutation({
    mutationFn: ({
      reportId,
      materialId,
      view = "slides",
    }: {
      reportId: string;
      materialId: string;
      view?: "slides";
    }) => api.reports.render(caseId, reportId, materialId, view),
  });
}
