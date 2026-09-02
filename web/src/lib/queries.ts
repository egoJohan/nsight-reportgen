import {
  useQuery,
  useMutation,
  useQueryClient,
  keepPreviousData,
  type QueryClient,
} from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api, ApiError } from "./api";
import { imageFingerprint, type RenderContext } from "./previewFingerprint";
import * as previewQueue from "./previewQueue";
import { noteCacheCleared } from "./previewCacheSignal";
import type { Substitutions } from "./api";
import type {
  AccessMode,
  ChartSpec,
  ChartPreviewTitleMeta,
  ReportDoc,
  GroupingOverride,
  WordMerge,
  UserGrantInput,
} from "./api";

/** The HTTP status behind a failed query, or null for anything that isn't
 *  one of `json()`'s `ApiError`s (a network failure, say). Lets a component
 *  tell "you may not see this" (404, spec §5 — absence, not refusal) apart
 *  from a fetch that just needs retrying. */
export function statusOf(error: unknown): number | null {
  return error instanceof ApiError ? error.status : null;
}

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
    // No polling here. This list costs the server one storage read per report
    // and one per lock, and re-fetching it every three seconds to keep a
    // badge honest spent ~78 round-trips to answer a question the server
    // holds in memory. `useCaseRenders` polls that instead and refreshes this
    // once, when a render actually finishes.
  });
}

/** Which reports in the case are rendering right now.
 *
 *  Polled while any of them is, and only then — the same trigger the list's
 *  own refetchInterval used, so a render started in another browser is still
 *  picked up exactly when it was before, at a fraction of the cost. When the
 *  set empties, the list is refreshed once so "Generated" and its timestamp
 *  land. */
export function useCaseRenders(caseId: string | null, active: boolean) {
  const qc = useQueryClient();
  const wasRendering = useRef(false);
  const query = useQuery({
    queryKey: ["case-renders", caseId ?? ""],
    queryFn: () => api.reports.renderingInCase(caseId!),
    enabled: !!caseId && active,
    refetchInterval: (q) =>
      (q.state.data?.rendering.length ?? 0) > 0 ? 3000 : false,
  });
  const busy = (query.data?.rendering.length ?? 0) > 0;
  useEffect(() => {
    if (wasRendering.current && !busy && caseId) {
      qc.invalidateQueries({ queryKey: qk.caseReports(caseId) });
    }
    wasRendering.current = busy;
  }, [busy, caseId, qc]);
  return new Set(query.data?.rendering ?? []);
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

/** Rename a customer. Its name is shown in the sidebar tree, the breadcrumb,
 *  the customer list and on every grant row, so the invalidation is broad on
 *  purpose — a rename that left the old name in three other places would read
 *  as a rename that failed. */
export function useRenameCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ customerId, name }: { customerId: string; name: string }) =>
      api.customers.rename(customerId, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["customer"] });
      qc.invalidateQueries({ queryKey: ["customers"] });
      // The grants screen shows a customer BY NAME beside each grant.
      qc.invalidateQueries({ queryKey: ["users"] });
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
      // A stand-in font is not part of the fingerprint either: same reasoning
      // as the chart font above.
      qc.removeQueries({ queryKey: ["chart-preview"] });
      previewQueue.restartDeck("a font substitution changed");
    },
  });
  return { ...query, save };
}

/** How many PICTURES this backend can usefully draw at once.
 *
 *  Asked once and cached for the session: it is a property of the machine, not
 *  of anything the author does. The queue starts at one and is raised when the
 *  answer arrives, so a slow or failed call leaves the SAFE setting in place
 *  rather than the fast one.
 *
 *  It bounds the drawing only. Slide passes go on overlapping, so a cold deck
 *  writes its headlines in parallel — which is where a first open spends most
 *  of its time — while the pictures are drawn at the pace the host can manage.
 */
export function useRenderCapacity() {
  const query = useQuery({
    queryKey: ["render-capacity"],
    queryFn: api.health,
    staleTime: Infinity,
    retry: 1,
  });
  const n = query.data?.render_concurrency;
  useEffect(() => {
    if (n) previewQueue.setRenderConcurrency(n);
  }, [n]);
  return n;
}

/** Throw away every rendered preview for this material, and say so.
 *
 *  Three things happen, and they are three because they are three different
 *  caches: the server's PNGs on disk, this browser's copies of them, and the
 *  queue's record of what it has already drawn. Clearing any two of them looks
 *  like the button did nothing — the pictures come straight back from whichever
 *  one was left.
 *
 *  It does NOT re-render here. Whether that should happen depends on which step
 *  the author is on, which is the wizard's business; this announces the fact
 *  and the wizard decides. See previewCacheSignal.
 */
export function useClearPreviewCache(materialId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.materials.clearPreviewCache(materialId!),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ["chart-preview"] });
      noteCacheCleared();
    },
  });
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
      // Every rendered thumbnail was drawn with the previous font. The font is
      // not part of the image fingerprint — it is a server-side setting, not a
      // property of the slide — so the pictures have to be dropped and made
      // again, and the queue has to be told, or it will consider them done.
      qc.removeQueries({ queryKey: ["chart-preview"] });
      previewQueue.restartDeck("the chart font changed");
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
    // NOT removeQueries any more, and the difference is the whole bug.
    //
    // Previews ARE keyed on the template now — it is part of the image
    // fingerprint — so a template change asks for different keys and the old
    // template's pictures are simply never looked up again. Wiping the cache on
    // top of that was actively destructive: this runs when the mutation
    // settles, by which time the queue has already rendered slides under the
    // NEW key, and it deleted those. The queue had recorded them as done, so
    // nothing rendered them a second time, and the pane stayed blank for ever
    // however long you waited. That is the "preview never gets ready" this
    // chased for days.
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

/** Every customer's id and name, including ones this user cannot open.
 *  Paired with useCustomers (which is grant-filtered) the difference is
 *  exactly the set they may request access to. */
export function useCustomerNames() {
  return useQuery({
    queryKey: ["customers", "names"],
    queryFn: () => api.customers.listNames(),
    staleTime: 60_000,
  });
}

export function useCustomer(customerId: string | undefined) {
  return useQuery({
    queryKey: ["customer", customerId],
    queryFn: () => api.customers.get(customerId!),
    enabled: !!customerId,
    // An ungranted customer 404s (spec §5) — expected for the no-access
    // page's caller, not worth retrying before it can show that page.
    retry: false,
  });
}

export function useCustomerCases(customerId: string | undefined) {
  return useQuery({
    queryKey: ["customer", customerId, "cases"],
    queryFn: () => api.customers.listCases(customerId!),
    enabled: !!customerId,
    retry: false,
  });
}

/** Id and name only — the one thing a customer page may show someone with no
 *  grant on it (see api.customers.getName). Used by NoAccessCustomer.tsx,
 *  fetched independently of `useCustomer` so it still resolves when THAT
 *  query 404s. */
export function useCustomerName(customerId: string | undefined) {
  return useQuery({
    queryKey: ["customer", customerId, "name"],
    queryFn: () => api.customers.getName(customerId!),
    enabled: !!customerId,
    retry: false,
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
  // One fingerprint, computed by exclusion — see previewFingerprint.ts. The
  // 25-field allow-list this replaced had to be remembered every time ChartSpec
  // gained a field, and forgetting meant the preview silently kept showing the
  // previous image.
  const queryKey = [
    "chart-preview",
    materialId,
    imageFingerprint(chart, {
      templateRef: opts?.templateRef ?? "",
      reportId: opts?.reportId ?? "",
      groupingKey,
      renderTitle,
    }),
  ];
  const priority = opts?.priority ?? false;
  const slideId = chart.slide_id ?? "";
  // The slide the author is looking at renders next. The queue owns ordering,
  // so this is not a second lane: whichever slide is selected goes to the head
  // of the one queue.
  //
  // It TELLS the queue which slide that is, rather than promoting it once. This
  // effect only re-runs when the selection changes, so a one-off promotion
  // ordered the work outstanding at that moment and nothing after it — and the
  // work that matters most comes after it, when the author types a headline
  // into the slide they are looking at and it is queued again, at the back.
  useEffect(() => {
    if (priority && slideId) previewQueue.setFocused(slideId);
  }, [priority, slideId]);

  // Keep the previous picture only while looking at the SAME slide.
  //
  // Holding it across a change of slide is how the Design pane appeared to
  // freeze after a template switch: every slide's image was being remade, the
  // one you clicked was not ready, and `keepPreviousData` filled the gap with
  // the picture of the slide you had just left. Clicking through the deck
  // showed one unchanging image. Editing a slide still keeps its own last
  // picture up, dimmed, which is what that behaviour is for.
  // Record what this component is asking for, next to what the queue rendered.
  const qcForNote = useQueryClient();
  useEffect(() => {
    if (!slideId) return;
    previewQueue.noteWanted(
      slideId,
      String(queryKey[2] ?? ""),
      qcForNote.getQueryData(queryKey) !== undefined
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slideId, String(queryKey[2] ?? "")]);

  const lastSlide = useRef(slideId);
  const sameSlide = lastSlide.current === slideId;
  lastSlide.current = slideId;

  // Cache-only. The preview queue is the ONLY thing that fetches an image, so
  // that a slide's headline is written before its picture is drawn and the
  // slide is rendered once rather than twice. A component that fetched on its
  // own would be a second queue again, which is the arrangement this replaced.
  return useQuery<ChartPreviewResult>({
    queryKey,
    queryFn: () => Promise.reject(new Error("previews are produced by previewQueue")),
    enabled: false,
    staleTime: Infinity,
    // Ten minutes, not thirty. Every entry here is a base64 PNG — a few hundred
    // KB — and a new one appears for every slide under every template anyone
    // switches to, so a deck of sixty and a few template changes is tens of MB
    // held in the tab. gcTime only evicts entries nothing is OBSERVING, so this
    // never takes the picture out from under a slide on screen; the cost is a
    // re-render for a slide nobody has looked at for ten minutes, which the
    // fast path does in about a fifth of a second.
    gcTime: 10 * 60_000,
    retry: false,
    placeholderData: sameSlide ? keepPreviousData : undefined,
  });
}

/** The cache key an image is stored under. Shared with the queue's `chart`
 *  producer so the thing that fetches and the thing that reads cannot drift. */
export function chartPreviewKey(
  materialId: string,
  chart: ChartSpec,
  ctx: RenderContext
): unknown[] {
  return ["chart-preview", materialId, imageFingerprint(chart, ctx)];
}

/** Fetch one slide's image into the cache, under the fingerprint the QUEUE
 *  computed. Called by the queue, nowhere else.
 *
 *  The fingerprint is passed in rather than recomputed here, and that is the
 *  whole point. It used to be recomputed from a render context captured in a
 *  closure — and a template change refills the queue synchronously, starting
 *  renders before the new closure is installed. Those renders stored their
 *  picture under the OLD template's key while the queue recorded the new one as
 *  done, so every slide was rendered, the queue reported itself finished, and
 *  the screen stayed blank. One fingerprint, computed once, used for both the
 *  key and the "do I have it?" check.
 */
export async function fetchChartPreviewInto(
  qc: QueryClient,
  materialId: string,
  chart: ChartSpec,
  fingerprint: string,
  opts: {
    renderTitle: boolean;
    reportId: string;
    grouping: GroupingOverride | undefined;
    /** The template this fingerprint was computed FOR — sent to the server so
     *  the picture cannot be drawn on a different one. */
    templateRef: string;
  }
): Promise<void> {
  await qc.fetchQuery<ChartPreviewResult>({
    queryKey: ["chart-preview", materialId, fingerprint],
    queryFn: () =>
      api.materials
        .previewChart(materialId, chart, {
          renderTitle: opts.renderTitle,
          grouping: opts.grouping,
          reportId: opts.reportId,
          templateRef: opts.templateRef,
        })
        .then(async ({ blob, titleMeta }) => ({
          dataUrl: await blobToDataURL(blob),
          titleMeta,
        })),
    staleTime: Infinity,
    gcTime: 10 * 60_000,   // matches the reader above
    retry: false,
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
      qc.removeQueries({ queryKey: ["chart-preview"] });
      previewQueue.restartDeck("word merges changed");
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
      qc.removeQueries({ queryKey: ["chart-preview"] });
      previewQueue.restartDeck("a question was renamed");
    },
  });
}

export function useCreateReport(caseId: string) {
  return useMutation({
    mutationFn: (report: ReportDoc) => api.reports.create(caseId, report),
  });
}

/** What must never reach an LLM from this dataset. */
export function useSensitiveTerms(materialId: string | undefined) {
  return useQuery({
    queryKey: ["sensitive-terms", materialId],
    queryFn: () => api.materials.sensitiveTerms(materialId!),
    enabled: !!materialId,
  });
}

export function useAcceptSensitiveTerms(materialId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (terms: string[]) =>
      api.materials.acceptSensitiveTerms(materialId!, terms),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sensitive-terms", materialId] });
      // The report list's create button is gated on this, so it has to hear.
      qc.invalidateQueries({ queryKey: ["case-reports"] });
    },
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
    // Mark the cached document stale, but do NOT pull it back right now.
    //
    // The saver already holds the authoritative version — it is what we just
    // sent — so refetching teaches us nothing, and a plain invalidate made every
    // save of a 60-chart report cost a PUT *and* a full GET. `refetchType:
    // "none"` keeps the freshness guarantee (anything mounting later, or this
    // query on its next observer, fetches the server's copy) without the round
    // trip behind each save.
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({
        queryKey: qk.report(caseId, vars.reportId),
        refetchType: "none",
      }),
  });
}

export function useDuplicateReport(caseId: string) {
  return useMutation({
    mutationFn: ({ reportId, name }: { reportId: string; name: string }) =>
      api.reports.duplicate(caseId, reportId, name),
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

export function useCancelRender(caseId: string) {
  return useMutation({
    mutationFn: (reportId: string) => api.reports.cancelRender(caseId, reportId),
  });
}

/** Polls while a render is in progress, so a page that just loaded (or
 *  reloaded) — including one that did not start the render itself — can tell
 *  "generating" apart from "not rendered". Stops polling once idle. */
export function useRenderStatus(caseId: string, reportId: string | null) {
  return useQuery({
    queryKey: ["render-status", caseId, reportId ?? ""],
    queryFn: () => api.reports.renderStatus(caseId, reportId!),
    enabled: !!reportId,
    refetchInterval: (query) => (query.state.data?.rendering ? 1500 : false),
  });
}

export function useUsers() {
  return useQuery({ queryKey: ["users"], queryFn: api.users.list });
}

/** The grant picker's customer list -- admin-only and NOT grant-filtered
 *  (see api.users.listGrantableCustomers). Only the Users screen's
 *  GrantPicker should use this; everywhere else that lists customers wants
 *  `useCustomers`, which respects the caller's grants. */
export function useGrantableCustomers() {
  return useQuery({ queryKey: ["users", "customers"], queryFn: api.users.listGrantableCustomers });
}

export function useUserActions() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["invites"] });
  };
  return {
    setGrants: useMutation({
      mutationFn: ({ userId, grants }: { userId: string; grants: UserGrantInput[] }) =>
        api.users.setGrants(userId, grants),
      onSuccess: invalidate,
    }),
    setAdmin: useMutation({
      mutationFn: ({ userId, isAdmin }: { userId: string; isAdmin: boolean }) =>
        api.users.setAdmin(userId, isAdmin),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: api.users.remove, onSuccess: invalidate }),
    invite: useMutation({
      mutationFn: ({ email, grants }: { email: string; grants: UserGrantInput[] }) =>
        api.users.invite(email, grants),
      onSuccess: invalidate,
    }),
    revokeInvite: useMutation({ mutationFn: api.users.revokeInvite, onSuccess: invalidate }),
  };
}

// ---- Access requests (the no-access page's "Request access" button, and
// the admin queue that acts on it — see api.accessRequests) ----

/** The signed-in caller's own requests — what the no-access page checks so
 *  a reload shows "you already asked, pending" instead of the button again. */
export function useMyAccessRequests() {
  return useQuery({ queryKey: ["access-requests", "mine"], queryFn: api.accessRequests.mine });
}

/** The queue: PENDING requests only, scoped server-side to what the caller
 *  may decide — every one for an admin, just their own customers' for an
 *  owner (see routes_access_requests.py's `list_access_requests`). Settings
 *  > Permission requests is the one place this is read; `enabled` lets that
 *  page skip the request entirely for someone who cannot see the tab at
 *  all, rather than firing it and discarding an always-empty result. */
export function useAccessRequests(enabled = true) {
  return useQuery({
    queryKey: ["access-requests"],
    queryFn: api.accessRequests.list,
    enabled,
  });
}

export function useAccessRequestActions() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["access-requests"] });
    // Approving writes a grant, same as the Users screen's own grant editor.
    qc.invalidateQueries({ queryKey: ["users"] });
  };
  return {
    create: useMutation({
      mutationFn: ({ customerId, mode }: { customerId: string; mode: AccessMode }) =>
        api.accessRequests.create(customerId, mode),
      onSuccess: invalidate,
    }),
    approve: useMutation({ mutationFn: api.accessRequests.approve, onSuccess: invalidate }),
    refuse: useMutation({ mutationFn: api.accessRequests.refuse, onSuccess: invalidate }),
  };
}
