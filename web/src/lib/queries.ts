import {
  useQuery,
  useMutation,
  useQueryClient,
  keepPreviousData,
} from "@tanstack/react-query";
import { useEffect } from "react";
import { api, setActivePreviewKey } from "./api";
import type { Substitutions } from "./api";
import type {
  ChartSpec,
  ChartPreviewTitleMeta,
  ReportDoc,
  GroupingOverride,
  WordMerge,
} from "./api";

// ---- Query keys ----
export const qk = {
  cases: () => ["cases"] as const,
  chartTypes: () => ["chart-types"] as const,
  questions: (materialId: string) => ["questions", materialId] as const,
  variables: (materialId: string) => ["variables", materialId] as const,
  report: (caseId: string, reportId: string) =>
    ["report", caseId, reportId] as const,
  caseMaterials: (caseId: string) => ["case-materials", caseId] as const,
  caseReports: (caseId: string) => ["case-reports", caseId] as const,
};

// ---- Case-scoped, server-side listings (so any user/device sees them) ----
export function useCaseMaterials(caseId: string | null) {
  return useQuery({
    queryKey: qk.caseMaterials(caseId ?? ""),
    queryFn: () => api.materials.listForCase(caseId!),
    enabled: !!caseId,
  });
}

export function useCaseReports(caseId: string | null) {
  return useQuery({
    queryKey: qk.caseReports(caseId ?? ""),
    queryFn: () => api.reports.listForCase(caseId!),
    enabled: !!caseId,
  });
}

// ---- Hooks ----

export function useRenameCustomerCase(customerId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId, name }: { caseId: string; name: string }) =>
      api.customers.renameCase(customerId!, caseId, name),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ["customer", customerId, "cases"] });
      qc.invalidateQueries({ queryKey: ["case", v.caseId, "resolve"] });
    },
  });
}

export function useResolvedCase(caseId: string | undefined) {
  return useQuery({
    queryKey: ["case", caseId, "resolve"],
    queryFn: () => api.customers.resolveCase(caseId!),
    enabled: !!caseId,
    // A legacy case has no customer, so a 404 here is expected, not an error
    // worth retrying.
    retry: false,
  });
}

export function useRecentReports(limit = 10) {
  return useQuery({
    queryKey: ["reports", "recent", limit],
    queryFn: () => api.customers.recentReports(limit),
  });
}

/** Fonts installed on the render host, and what the templates still need. */
export function useFontSettings() {
  return useQuery({ queryKey: ["settings", "fonts"], queryFn: api.settings.fonts });
}

export function useTemplateDetail(
  customerId: string | undefined,
  templateId: string | undefined
) {
  return useQuery({
    queryKey: ["template-detail", customerId, templateId],
    queryFn: () => api.templates.detail(customerId!, templateId!),
    enabled: !!customerId && !!templateId,
  });
}

export function useSubstitutions() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["settings", "substitutions"],
    queryFn: api.settings.substitutions,
  });
  const save = useMutation({
    mutationFn: api.settings.setSubstitutions,
    // Applied to the cache before the request goes out. The dropdown is bound
    // to this query, so without it the control keeps showing the OLD font
    // until the round trip returns — which reads as the control being broken
    // rather than as the save being slow.
    onMutate: async (map) => {
      const key = ["settings", "substitutions"];
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<Substitutions>(key);
      if (previous) qc.setQueryData<Substitutions>(key, { ...previous, map });
      return { previous };
    },
    onError: (_e, _map, ctx) => {
      // Put the real state back: the select must never keep showing a choice
      // the server rejected.
      if (ctx?.previous) {
        qc.setQueryData(["settings", "substitutions"], ctx.previous);
      }
    },
    onSettled: () => {
      // A stand-in changes what every template resolves to and what every
      // rendered preview looks like. These refetch in the background; the
      // control is already correct.
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["template-detail"] });
      qc.invalidateQueries({ queryKey: ["templates"] });
      qc.invalidateQueries({ queryKey: ["chart-preview"] });
    },
  });
  return { ...query, save };
}

export function useChartFont() {
  return useQuery({
    queryKey: ["settings", "chart-font"],
    queryFn: api.settings.chartFont,
  });
}

export function useSetChartFont() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.settings.setChartFont,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings", "chart-font"] });
      // Every rendered thumbnail was drawn with the previous font.
      qc.invalidateQueries({ queryKey: ["chart-preview"] });
    },
  });
}

export function useFontActions() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["settings", "fonts"] });
    // Installing a font changes what every template resolves to, so the
    // template panels' "font missing" flags are stale the moment this lands.
    qc.invalidateQueries({ queryKey: ["templates"] });
  };
  return {
    upload: useMutation({ mutationFn: api.settings.uploadFont, onSuccess: invalidate }),
    remove: useMutation({ mutationFn: api.settings.deleteFont, onSuccess: invalidate }),
  };
}

export function useTemplates(customerId: string | undefined) {
  return useQuery({
    queryKey: ["templates", customerId],
    queryFn: () => api.templates.list(customerId!),
    enabled: !!customerId,
  });
}

export function useReportTemplate(
  customerId: string | undefined,
  caseId: string | undefined,
  reportId: string | undefined
) {
  return useQuery({
    queryKey: ["template", customerId, caseId, reportId],
    queryFn: () => api.templates.forReport(customerId!, caseId!, reportId!),
    enabled: !!customerId && !!caseId && !!reportId,
  });
}

/** What a tutkimus resolves to with no report in play. Shares the "template"
 *  key prefix so a bind at any level invalidates it. */
export function useCaseTemplate(
  customerId: string | undefined,
  caseId: string | undefined
) {
  return useQuery({
    queryKey: ["template", customerId, caseId],
    queryFn: () => api.templates.forCase(customerId!, caseId!),
    enabled: !!customerId && !!caseId,
  });
}

/** Every template mutation invalidates both lists and resolutions: binding at
 *  one level changes what the levels below resolve to. */
export function useTemplateActions(customerId: string | undefined) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["templates", customerId] });
    qc.invalidateQueries({ queryKey: ["template"] });
    // The binding lives ON the customer/case record, so those queries are stale
    // too — without this the panel keeps showing the previous state.
    qc.invalidateQueries({ queryKey: ["customer"] });
    qc.invalidateQueries({ queryKey: ["customers"] });
    qc.invalidateQueries({ queryKey: ["case"] });
    // Every chart preview is a picture of a slide IN a template — its ground,
    // its title font, its palette — so changing the template makes all of them
    // wrong. They are not keyed on the template (the chart's own content is the
    // key), so they are REMOVED rather than invalidated: dropped from the cache
    // and re-rendered on demand, instead of showing the old template's slide
    // until something else happens to refetch them.
    qc.removeQueries({ queryKey: ["chart-preview"] });
  };
  return {
    upload: useMutation({
      mutationFn: (file: File) => api.templates.upload(customerId!, file),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (templateId: string) => api.templates.remove(customerId!, templateId),
      onSuccess: invalidate,
    }),
    bindCustomer: useMutation({
      mutationFn: (templateId: string | null) =>
        api.templates.bindCustomer(customerId!, templateId),
      onSuccess: invalidate,
    }),
    bindCase: useMutation({
      mutationFn: (v: { caseId: string; templateId: string | null }) =>
        api.templates.bindCase(customerId!, v.caseId, v.templateId),
      onSuccess: invalidate,
    }),
    bindReport: useMutation({
      mutationFn: (v: { caseId: string; reportId: string; templateId: string | null }) =>
        api.templates.bindReport(customerId!, v.caseId, v.reportId, v.templateId),
      onSuccess: invalidate,
    }),
    refreshReport: useMutation({
      mutationFn: (v: { caseId: string; reportId: string }) =>
        api.templates.refreshReport(customerId!, v.caseId, v.reportId),
      onSuccess: invalidate,
    }),
  };
}

export function useCustomers() {
  return useQuery({ queryKey: ["customers"], queryFn: api.customers.list });
}

export function useCustomer(customerId: string | undefined) {
  return useQuery({
    queryKey: ["customer", customerId],
    queryFn: () => api.customers.get(customerId!),
    enabled: !!customerId,
  });
}

export function useCustomerCases(customerId: string | undefined) {
  return useQuery({
    queryKey: ["customer", customerId, "cases"],
    queryFn: () => api.customers.listCases(customerId!),
    enabled: !!customerId,
  });
}

export function useCreateCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.customers.create(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["customers"] }),
  });
}

export function useCreateCustomerCase(customerId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.customers.createCase(customerId!, name),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["customer", customerId, "cases"] }),
  });
}

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
    classifying_var_2: chart.classifying_var_2 ?? null,
    // The cross-tab percentage DIRECTION changes the numbers in the PNG, so a change
    // must re-render the preview (else switching direction silently shows the old one).
    percent_base: chart.percent_base ?? "auto",
    // Showing/hiding the "Total" reference series changes the PNG too.
    show_total: chart.show_total ?? "auto",
    number_format: chart.number_format,
    sort: chart.sort,
    elements: chart.elements,
    scatter_xy: chart.scatter_xy,
    show_not_answered: chart.show_not_answered,
    show_empty_categories: chart.show_empty_categories,
    not_answered_codes: chart.not_answered_codes,
    category_label_overrides: chart.category_label_overrides,
    options: chart.options ?? null,
    // The methodology footer is baked into the PNG regardless of render_title (it lives
    // outside the title block), so a footer edit must always re-render the preview.
    footer_note: chart.footer_note,
    // The row-summary column (function/codes/header) is baked into the chart PNG, so
    // any change must re-render the preview.
    row_summary_fn: chart.row_summary_fn ?? "none",
    row_summary_codes: chart.row_summary_codes ?? null,
    row_summary_pos_codes: chart.row_summary_pos_codes ?? null,
    row_summary_neg_codes: chart.row_summary_neg_codes ?? null,
    row_summary_label: chart.row_summary_label ?? "",
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

export interface ChartPreviewResult {
  dataUrl: string;
  // Where the template puts its title, for a caller that draws it itself
  // (renderTitle: false). Null on the slow path and on a template with no
  // title box — see readTitleMeta in api.ts.
  titleMeta: ChartPreviewTitleMeta | null;
}

/**
 * A cached chart preview (data URL + the template's title box, when known).
 * Keyed by material + render-affecting chart fields + renderTitle, with
 * staleTime Infinity, so the same chart never re-renders: formed once, reused
 * everywhere (Configure, Review, Slides).
 *
 * renderTitle defaults to false: the fast (composited) preview path is only
 * ever taken when nothing bakes a title into the PNG, and nothing did before
 * this default changed — every caller asked for the baked title explicitly,
 * which is why every preview used to start LibreOffice. A caller that still
 * wants the full baked slide (the Design step's own live pane) passes
 * renderTitle: true.
 */
export function useChartPreview(
  materialId: string,
  chart: ChartSpec,
  opts?: {
    renderTitle?: boolean;
    enabled?: boolean;
    priority?: boolean;
    grouping?: GroupingOverride;
    // Which report this preview is for. reportId goes to the backend so
    // resolve_template can see the report's own template/pin (see
    // _preview_template in routes_questions.py). templateRef — the report's
    // OWN explicit choice, "" when it inherits one — is NOT sent; it exists
    // here purely to bust this cache entry the instant the user picks a new
    // template, same tick as the (separately fired) request that persists it.
    // Without it, picking a new template kept showing the old one's preview:
    // same content, same renderTitle, so the query key never changed and
    // nothing re-rendered.
    reportId?: string;
    templateRef?: string;
  }
) {
  const renderTitle = opts?.renderTitle ?? false;
  const groupingKey = JSON.stringify(opts?.grouping ?? {});
  const queryKey = [
    "chart-preview",
    materialId,
    opts?.reportId ?? "",
    opts?.templateRef ?? "",
    renderTitle,
    previewContentKey(chart, renderTitle),
    groupingKey,
  ];
  // Stable string key shared with the render gate so it can match this slide's
  // queued render and promote it when this slide is the active one.
  const gateKey = JSON.stringify(queryKey);
  const priority = opts?.priority ?? false;
  // The ACTIVE slide announces its key so the gate runs its render first (in the
  // reserved slot) even if the background prefetch already queued it.
  useEffect(() => {
    if (!priority) return;
    setActivePreviewKey(gateKey);
    return () => setActivePreviewKey(null);
  }, [priority, gateKey]);
  return useQuery<ChartPreviewResult>({
    queryKey,
    queryFn: () =>
      api.materials
        .previewChart(materialId, chart, {
          renderTitle,
          key: gateKey,
          grouping: opts?.grouping,
          reportId: opts?.reportId,
        })
        .then(async ({ blob, titleMeta }) => ({
          dataUrl: await blobToDataURL(blob),
          titleMeta,
        })),
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
    // The catalog is nearly static, but it DOES change when the backend gains a new
    // plugin/config field — cache it for 5 min (and refetch on window focus) so new
    // config options appear without a hard reload, instead of staleTime: Infinity.
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
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

export function useQuestionSummary(
  materialId: string,
  qid: string | null,
  grouping?: GroupingOverride
) {
  return useQuery({
    queryKey: ["question-summary", materialId, qid ?? "", grouping ?? null],
    queryFn: () => api.materials.questionSummary(materialId, qid!, grouping),
    enabled: !!materialId && !!qid,
    staleTime: 5 * 60_000,
  });
}

export function useVariables(materialId: string | null, all = false) {
  return useQuery({
    queryKey: [...qk.variables(materialId ?? ""), all ? "all" : "default"],
    queryFn: () => api.materials.variables(materialId!, { all }),
    enabled: !!materialId,
    select: (d) => d.variables,
  });
}

// Questions reshaped by a report's grouping override (stateless preview).
export function useRegroupedQuestions(
  materialId: string | null,
  grouping: GroupingOverride
) {
  return useQuery({
    queryKey: ["regrouped-questions", materialId ?? "", JSON.stringify(grouping)],
    queryFn: () => api.materials.regroup(materialId!, grouping),
    enabled: !!materialId,
    select: (d) => d.questions,
    // Keep the prior reshaping visible while a new grouping reshapes, so the group
    // list doesn't flash empty between edits.
    placeholderData: keepPreviousData,
  });
}

// Battery suggestions for the current grouping — shares the regroup query cache
// (same key), so no extra fetch. Runs of ≥3 contiguous same-scale variables.
export function useBatterySuggestions(
  materialId: string | null,
  grouping: GroupingOverride
) {
  return useQuery({
    queryKey: ["regrouped-questions", materialId ?? "", JSON.stringify(grouping)],
    queryFn: () => api.materials.regroup(materialId!, grouping),
    enabled: !!materialId,
    select: (d) => d.battery_suggestions ?? [],
  });
}

// Parallel-question suggestions for the current grouping — shares the regroup query
// cache (same key). Sets of questions that share a category set (adjectives sharing
// services), seeding the comparison suggestions in the group manager.
export function useParallelSuggestions(
  materialId: string | null,
  grouping: GroupingOverride
) {
  return useQuery({
    queryKey: ["regrouped-questions", materialId ?? "", JSON.stringify(grouping)],
    queryFn: () => api.materials.regroup(materialId!, grouping),
    enabled: !!materialId,
    select: (d) => d.parallel_suggestions ?? [],
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

// Word-cloud editing for a text question: raw top words + current merges.
export function useQuestionWords(materialId: string, qid: string | null) {
  return useQuery({
    queryKey: ["question-words", materialId, qid ?? ""],
    queryFn: () => api.materials.questionWords(materialId, qid!),
    enabled: !!materialId && !!qid,
    staleTime: 5 * 60_000,
  });
}

export function useSetWordMerges(materialId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ qid, merges }: { qid: string; merges: WordMerge[] }) =>
      api.materials.setWordMerges(materialId, qid, merges),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["question-words", materialId] });
      qc.invalidateQueries({ queryKey: ["chart-preview"] });
      qc.invalidateQueries({ queryKey: ["question-summary", materialId] });
    },
  });
}

// Rename a question for this material (case-page edit). Invalidates every view
// that renders a question's text so the rename appears immediately.
export function useSetQuestionLabel(materialId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ qid, label }: { qid: string; label: string }) =>
      api.materials.setQuestionLabel(materialId, qid, label),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.questions(materialId) });
      qc.invalidateQueries({ queryKey: ["question-summary", materialId] });
      qc.invalidateQueries({ queryKey: ["regrouped-questions", materialId] });
      qc.invalidateQueries({ queryKey: ["chart-preview"] });
    },
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
      signal,
    }: {
      reportId: string;
      materialId: string;
      view?: "slides";
      signal?: AbortSignal;
    }) => api.reports.render(caseId, reportId, materialId, view, signal),
  });
}
