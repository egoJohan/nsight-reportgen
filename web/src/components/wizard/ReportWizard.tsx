import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckIcon,
  ChevronLeftIcon,
  FileXIcon,
  Loader2Icon,
  PencilIcon,
  SaveIcon,
  XIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn, formatReportDate } from "@/lib/utils";
import { api } from "@/lib/api";
import type { ChartSpec, Question, ReportDoc } from "@/lib/api";
import { useReport, useUpdateReport, useQuestions } from "@/lib/queries";
import { useWorkspace } from "@/lib/workspace";
import {
  buildDemographicsGrids,
  buildSpecialPages,
  isSpecialSlide,
  isThemes,
  makeChart,
  makeSpecialSlide,
  normalizeSlots,
} from "@/lib/charts";
import StepSelect from "./StepSelect";
import StepConfigure from "./StepConfigure";
import StepDownload from "./StepDownload";

/** Move an item within an array, returning a new array. */
function move<T>(arr: T[], from: number, to: number): T[] {
  if (to < 0 || to >= arr.length || from === to) return arr;
  const next = arr.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

/** Replace every chart belonging to a special-slide `group` (its anchor ref or
 *  any member tagged options.group === group) with `pages`, inserting
 *  `extraAfter` immediately after them. Returns null if the group is gone (the
 *  slide was removed mid-generation). */
function replaceSpecialGroup(
  charts: ChartSpec[],
  group: string,
  pages: ChartSpec[],
  extraAfter: ChartSpec[] = []
): ChartSpec[] | null {
  let inserted = false;
  const out: ChartSpec[] = [];
  for (const c of charts) {
    const inGroup = c.question_ref === group || c.options?.group === group;
    if (inGroup) {
      if (!inserted) {
        out.push(...pages, ...extraAfter);
        inserted = true;
      }
    } else {
      out.push(c);
    }
  }
  return inserted ? out : null;
}

const STEPS = [
  { id: "select", label: "Select" },
  { id: "configure", label: "Design" },
  { id: "download", label: "Download" },
];

// Per-phase instruction shown centered under the stepper (report-specific).
const STEP_INSTRUCTIONS = [
  "Toggle a question to add or remove its chart from the report, then press Next.",
  "",
  "",
];

function Stepper({
  current,
  onJump,
  chartCount,
}: {
  current: number;
  onJump: (i: number) => void;
  chartCount: number;
}) {
  return (
    <div className="flex items-center">
      {STEPS.map((s, i) => {
        const done = i < current;
        const active = i === current;
        const future = i > current;
        // All steps reachable; Download (last step) requires at least one chart.
        const reachable = i < STEPS.length - 1 || chartCount > 0;
        return (
          <div key={s.id} className="flex items-center">
            <button
              disabled={!reachable}
              onClick={() => reachable && onJump(i)}
              className={cn(
                "flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
                reachable && "hover:bg-muted",
                !reachable && "cursor-default"
              )}
            >
              <span
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-medium tabular-nums transition-colors",
                  active && "bg-primary text-primary-foreground",
                  done && "bg-primary/15 text-primary",
                  future && "bg-muted text-muted-foreground"
                )}
              >
                {done ? <CheckIcon className="size-3.5" /> : i + 1}
              </span>
              <span
                className={cn(
                  "font-medium",
                  active && "text-foreground",
                  !active && "text-muted-foreground"
                )}
              >
                {s.label}
              </span>
            </button>
            {i < STEPS.length - 1 && (
              <div className="mx-1 h-px w-6 bg-border" />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function ReportWizard({
  caseId,
  reportId,
  materialId,
  onClose,
  onMissing,
}: {
  caseId: string;
  reportId: string;
  materialId: string;
  onClose: () => void;
  onMissing?: () => void;
}) {
  const { data: loaded, isLoading, isError } = useReport(caseId, reportId);
  const updateReport = useUpdateReport(caseId);
  const { workspace, renameReport } = useWorkspace(caseId);
  const createdAt = workspace.reports.find((r) => r.id === reportId)?.createdAt;
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");

  const [draft, setDraft] = useState<ReportDoc | null>(null);
  const [step, setStep] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  // Per-chart pending flags (keyed by question_ref) so the Configure preview
  // can show "Generating title…" / "Shortening labels…" placeholders over the
  // regions that are still being produced. Set true when a chart's AI call
  // starts, false when it resolves/fails.
  const [aiPending, setAiPending] = useState<
    Record<
      string,
      { titlePending: boolean; labelsPending: boolean; bulletsPending?: boolean }
    >
  >({});

  // Initialise the working draft once the report loads.
  useEffect(() => {
    if (loaded && !draft) {
      setDraft({
        name: loaded.name,
        render_mode: "image",
        template_ref: loaded.template_ref ?? "",
        charts: loaded.charts ?? [],
        grouping: loaded.grouping ?? { groups: [], singles: [] },
      });
    }
  }, [loaded, draft]);

  const addedRefs = useMemo(
    () => new Set((draft?.charts ?? []).map((c) => c.question_ref)),
    [draft]
  );

  const mutate = useCallback(
    (fn: (d: ReportDoc) => ReportDoc) => {
      setDraft((prev) => (prev ? fn(prev) : prev));
      setDirty(true);
    },
    []
  );

  // Drop charts whose question no longer exists (e.g. its variable was absorbed
  // into a group, or a group was split away) so Design never shows a dangling
  // ref like "var7" that errors on preview.
  const pruneToValidRefs = useCallback(
    (valid: Set<string>) => {
      mutate((d) => {
        const kept = d.charts.filter((c) => valid.has(c.question_ref));
        return kept.length === d.charts.length ? d : { ...d, charts: kept };
      });
    },
    [mutate]
  );

  // SAV (questionnaire) order: rank each question by its position in the source
  // file so newly added slides land in questionnaire order, matching how the
  // source decks are sequenced (the user can still drag to reorder).
  const { data: orderedQuestions } = useQuestions(materialId);
  const qRank = useMemo(() => {
    const m = new Map<string, number>();
    // Demographics float to the front (rank offset); SAV order kept within each
    // group, matching the demographics-first seeding of a new report.
    (orderedQuestions ?? []).forEach((q, i) =>
      m.set(q.qid, q.is_demographic ? i - 100000 : i)
    );
    return m;
  }, [orderedQuestions]);

  // Enabling/disabling a question directly edits the report: add its chart when
  // absent (inserted in SAV order), remove it when present (no separate "Add
  // selected" step).
  const toggleQuestion = useCallback(
    (q: Question) => {
      mutate((d) => {
        const exists = d.charts.some((c) => c.question_ref === q.qid);
        if (exists) {
          return {
            ...d,
            charts: normalizeSlots(
              d.charts.filter((c) => c.question_ref !== q.qid)
            ),
          };
        }
        // Insert the new chart in SAV order: after any front special slides and
        // earlier-ranked question slides, before higher-ranked ones and a
        // trailing conclusion slide.
        const newRank = qRank.get(q.qid) ?? Number.POSITIVE_INFINITY;
        const charts = [...d.charts];
        let pos = charts.length;
        for (let i = 0; i < charts.length; i++) {
          const c = charts[i];
          if (isSpecialSlide(c)) {
            if (c.chart_type === "special_conclusion") {
              pos = i;
              break;
            }
            continue; // front special slide → insert after it
          }
          const r = qRank.get(c.question_ref) ?? Number.POSITIVE_INFINITY;
          if (r > newRank) {
            pos = i;
            break;
          }
        }
        charts.splice(pos, 0, makeChart(q.qid, q.suggested_chart_type));
        return { ...d, charts: normalizeSlots(charts) };
      });
    },
    [mutate, qRank]
  );

  // Batch add/remove charts for many questions at once (Select-phase "Select all /
  // Deselect all"). One mutate so it's a single undo step and never toggles each ref.
  const selectMany = useCallback(
    (questions: Question[], select: boolean) => {
      const qids = new Set(questions.map((q) => q.qid));
      mutate((d) => {
        if (!select) {
          // Drop these questions' charts; special slides (overview/conclusion) stay.
          return {
            ...d,
            charts: normalizeSlots(
              d.charts.filter((c) => isSpecialSlide(c) || !qids.has(c.question_ref))
            ),
          };
        }
        const present = new Set(
          d.charts.filter((c) => !isSpecialSlide(c)).map((c) => c.question_ref)
        );
        const additions = questions
          .filter((q) => !present.has(q.qid))
          .map((q) => makeChart(q.qid, q.suggested_chart_type));
        if (additions.length === 0) return d;
        // Rebuild: front special slides, then all question charts in SAV rank order,
        // then a trailing conclusion slide — matching single-toggle insertion.
        const front: ChartSpec[] = [];
        const conclusion: ChartSpec[] = [];
        const qCharts: ChartSpec[] = [];
        for (const c of d.charts) {
          if (isSpecialSlide(c)) {
            (c.chart_type === "special_conclusion" ? conclusion : front).push(c);
          } else qCharts.push(c);
        }
        const rank = (c: ChartSpec) =>
          qRank.get(c.question_ref) ?? Number.POSITIVE_INFINITY;
        const ordered = [...qCharts, ...additions].sort((a, b) => rank(a) - rank(b));
        return { ...d, charts: normalizeSlots([...front, ...ordered, ...conclusion]) };
      });
    },
    [mutate, qRank]
  );

  const updateChart = useCallback(
    (index: number, patch: Partial<ChartSpec>) => {
      mutate((d) => ({
        ...d,
        charts: d.charts.map((c, i) => (i === index ? { ...c, ...patch } : c)),
      }));
    },
    [mutate]
  );

  // Update a chart found by its question_ref (indices can shift while async
  // AI work is in flight, so the auto-formatter addresses charts by ref).
  const updateChartByRef = useCallback(
    (ref: string, patch: Partial<ChartSpec>) => {
      mutate((d) => ({
        ...d,
        charts: d.charts.map((c) =>
          c.question_ref === ref ? { ...c, ...patch } : c
        ),
      }));
    },
    [mutate]
  );

  const removeChart = useCallback(
    (index: number) => {
      mutate((d) => ({
        ...d,
        charts: normalizeSlots(d.charts.filter((_, i) => i !== index)),
      }));
    },
    [mutate]
  );

  const reorderCharts = useCallback(
    (from: number, to: number) => {
      mutate((d) => ({
        ...d,
        charts: normalizeSlots(move(d.charts, from, to)),
      }));
    },
    [mutate]
  );

  // Keep a ref to the latest draft for save() without stale closures.
  const draftRef = useRef<ReportDoc | null>(null);
  draftRef.current = draft;

  const save = useCallback(async (): Promise<boolean> => {
    const d = draftRef.current;
    if (!d) return false;
    const payload: ReportDoc = { ...d, charts: normalizeSlots(d.charts) };
    try {
      await updateReport.mutateAsync({ reportId, report: payload });
      setDirty(false);
      setSavedAt(Date.now());
      return true;
    } catch (e) {
      toast.error(
        `Save failed: ${e instanceof Error ? e.message : "unknown error"}`
      );
      return false;
    }
  }, [updateReport, reportId]);

  // Persist unsaved edits if the report is closed (e.g. via the top-bar close)
  // without going through a commit-then-navigate path. Refs keep the unmount
  // cleanup stable so it runs only on unmount.
  const saveRef = useRef(save);
  saveRef.current = save;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  useEffect(() => {
    return () => {
      if (dirtyRef.current) void saveRef.current();
    };
  }, []);

  // ── Auto AI slide titles (batched, like the chart thumbnails) ─────────────
  // When the Design step is open, titles are generated automatically for every
  // chart — the same way the thumbnails auto-render — NOT eagerly on report
  // load and NOT only for the chart you click. egoHive is slow and a report can
  // hold 100+ charts, so the work runs through a bounded-concurrency queue.
  // While a chart's title is in flight the preview covers the title band with a
  // dashed placeholder; the AI key-message replaces it automatically when it
  // lands. Graceful fallback to the question text on failure; one attempt per
  // ref per session.
  const TITLE_CONCURRENCY = 3;
  const titlesAttempted = useRef<Set<string>>(new Set());
  const titleQueue = useRef<string[]>([]);
  const titleActive = useRef(0);
  // Bumped when a batch drains; a separate effect then persists the result so
  // every generated patch has flushed into the draft before we read it.
  const [aiSaveTick, setAiSaveTick] = useState(0);

  const runTitle = useCallback(
    async (ref: string) => {
      const chart = draftRef.current?.charts.find(
        (c) => c.question_ref === ref
      );
      if (!chart) return;
      // A "themes" chart (open-ended) generates theme bullets AND an AI heading
      // (a key message from the answers) — otherwise it falls back to showing its
      // raw, often messy, question text as the title.
      if (isThemes(chart)) {
        const hasBullets = !!(chart.options?.bullets as string[] | undefined)
          ?.length;
        const bulletsP = hasBullets
          ? Promise.resolve()
          : api.materials
              .aiThemes(materialId, { question_ref: ref })
              .then(({ bullets }) =>
                updateChartByRef(ref, {
                  options: { ...(chart.options ?? {}), bullets },
                })
              )
              .catch(() => {
                /* graceful: leave empty */
              })
              .finally(() =>
                setAiPending((prev) => ({
                  ...prev,
                  [ref]: { ...prev[ref], bulletsPending: false },
                }))
              );
        const titleP = chart.slide_title
          ? Promise.resolve()
          : api.materials
              .aiSlideTitle(materialId, {
                question_ref: ref,
                statistic: chart.statistic,
              })
              .then(({ title }) => {
                if (title) updateChartByRef(ref, { slide_title: title });
              })
              .catch(() => {
                /* graceful: fall back to the question text */
              })
              .finally(() =>
                setAiPending((prev) => ({
                  ...prev,
                  [ref]: { ...prev[ref], titlePending: false },
                }))
              );
        await Promise.all([bulletsP, titleP]);
        return;
      }
      try {
        const { title } = await api.materials.aiSlideTitle(materialId, {
          question_ref: ref,
          statistic: chart.statistic,
          classifying_var: chart.classifying_var,
          show_not_answered: chart.show_not_answered,
          not_answered_codes: chart.not_answered_codes,
        });
        if (title) updateChartByRef(ref, { slide_title: title });
      } catch {
        /* graceful: fall back to the question text */
      } finally {
        setAiPending((prev) => ({
          ...prev,
          [ref]: { ...prev[ref], titlePending: false },
        }));
      }
    },
    [materialId, updateChartByRef]
  );

  const pumpTitles = useCallback(() => {
    while (
      titleActive.current < TITLE_CONCURRENCY &&
      titleQueue.current.length > 0
    ) {
      const ref = titleQueue.current.shift()!;
      titleActive.current += 1;
      void runTitle(ref).finally(() => {
        titleActive.current -= 1;
        if (titleActive.current === 0 && titleQueue.current.length === 0) {
          // Batch settled — persist all generated titles in one save.
          setAiSaveTick((t) => t + 1);
        }
        pumpTitles();
      });
    }
  }, [runTitle]);

  // Enqueue titles for every chart that still needs one (deduped; one attempt
  // per ref). Mark the title regions pending up front so their placeholders
  // appear immediately, then drain through the bounded queue.
  const ensureTitles = useCallback(
    (refs: string[]) => {
      let added = false;
      for (const ref of refs) {
        if (!ref || titlesAttempted.current.has(ref)) continue;
        const chart = draftRef.current?.charts.find(
          (c) => c.question_ref === ref
        );
        if (!chart) continue;
        if (isSpecialSlide(chart)) continue; // special slides carry bullets, not a title
        const themes = isThemes(chart);
        const needsBullets =
          themes && !((chart.options?.bullets as string[] | undefined)?.length);
        const needsTitle = !chart.slide_title;
        // Themes charts generate BOTH bullets and an AI heading; other charts
        // generate a title (unless they already have one).
        if (themes ? !needsBullets && !needsTitle : !needsTitle) continue;
        titlesAttempted.current.add(ref);
        titleQueue.current.push(ref);
        added = true;
        setAiPending((prev) => ({
          ...prev,
          [ref]: themes
            ? {
                titlePending: needsTitle,
                labelsPending: prev[ref]?.labelsPending ?? false,
                bulletsPending: needsBullets,
              }
            : {
                titlePending: true,
                labelsPending: prev[ref]?.labelsPending ?? false,
              },
        }));
      }
      if (added) pumpTitles();
    },
    [pumpTitles]
  );

  // Persist generated overrides/titles once an auto-format pass settles. Runs
  // post-commit so draftRef already reflects every generated patch.
  useEffect(() => {
    if (aiSaveTick === 0) return;
    void save();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aiSaveTick]);

  // ── Special (non-chart) slides: Overview / Conclusion / Demographics ──────
  const SPECIAL_HEADINGS: Record<string, string> = {
    special_overview: "Tutkimuksen taustaa",
    special_conclusion: "Johtopäätökset",
    special_demographics: "Vastaajat",
  };
  const errMsg = (e: unknown) => (e instanceof Error ? e.message : "unknown error");
  const reportQuestionRefs = useCallback(
    () =>
      (draftRef.current?.charts ?? [])
        .filter((c) => !isSpecialSlide(c))
        .map((c) => c.question_ref),
    []
  );
  const setBulletsPending = useCallback((ref: string, pending: boolean) => {
    setAiPending((prev) => ({
      ...prev,
      [ref]: {
        titlePending: prev[ref]?.titlePending ?? false,
        labelsPending: prev[ref]?.labelsPending ?? false,
        bulletsPending: pending,
      },
    }));
  }, []);
  const fetchBullets = useCallback(
    async (type: string, refs: string[]): Promise<string[]> => {
      if (type === "special_overview")
        return (await api.materials.aiOverview(materialId, { question_refs: refs })).bullets;
      return (await api.materials.aiConclusion(materialId, { question_refs: refs })).bullets;
    },
    [materialId]
  );

  // Lay out generated bullets across one-or-more pages (the first page keeps the
  // group's anchor ref so the current selection stays valid), replacing any
  // existing pages of this special-slide `group`. `extraAfter` (demographic
  // charts) is inserted right after the pages.
  const applySpecialPages = useCallback(
    (
      group: string,
      type: string,
      heading: string,
      bullets: string[],
      extraAfter: ChartSpec[] = []
    ) => {
      mutate((d) => {
        const pages = buildSpecialPages(type, heading, bullets, group).map((p, i) =>
          i === 0 ? { ...p, question_ref: group } : p
        );
        const next = replaceSpecialGroup(d.charts, group, pages, extraAfter);
        return next ? { ...d, charts: normalizeSlots(next) } : d;
      });
    },
    [mutate]
  );

  // Demographics: a (possibly multi-page) facts slide followed by demographics
  // grid slides (several compact charts per page). Replaces the whole group.
  const applyDemographics = useCallback(
    (
      group: string,
      heading: string,
      bullets: string[],
      cells: { question_ref: string; chart_type: string }[]
    ) => {
      mutate((d) => {
        const factPages = buildSpecialPages(
          "special_demographics",
          heading,
          bullets,
          group
        ).map((p, i) => (i === 0 ? { ...p, question_ref: group } : p));
        const gridPages = buildDemographicsGrids(cells ?? [], group);
        const next = replaceSpecialGroup(d.charts, group, [...factPages, ...gridPages]);
        return next ? { ...d, charts: normalizeSlots(next) } : d;
      });
    },
    [mutate]
  );

  // Add a special slide (synchronously, returning its anchor ref so the caller
  // can select it) and generate its bullets in the background — spanning pages
  // when the content overflows one slide.
  const addSpecialSlide = useCallback(
    (type: string, afterRef?: string | null): string => {
      const heading = SPECIAL_HEADINGS[type];
      const placeholder = makeSpecialSlide(type, { slide_title: heading });
      const group = placeholder.question_ref;
      const anchor = {
        ...placeholder,
        options: { ...placeholder.options, group },
      };
      // Insert right AFTER the active slide (so it lands where you're working);
      // with no active slide, go to the front of the deck.
      mutate((d) => {
        const charts = [...d.charts];
        const at = afterRef
          ? charts.findIndex((c) => c.question_ref === afterRef)
          : -1;
        if (at >= 0) charts.splice(at + 1, 0, anchor);
        else charts.unshift(anchor);
        return { ...d, charts: normalizeSlots(charts) };
      });
      setBulletsPending(group, true);
      void (async () => {
        try {
          if (type === "special_demographics") {
            const { bullets, charts } = await api.materials.aiDemographics(
              materialId,
              { question_refs: reportQuestionRefs() }
            );
            applyDemographics(group, heading, bullets, charts);
          } else {
            const bullets = await fetchBullets(type, reportQuestionRefs());
            applySpecialPages(group, type, heading, bullets);
          }
        } catch (e) {
          toast.error(`Could not generate slide: ${errMsg(e)}`);
        } finally {
          setBulletsPending(group, false);
          setAiSaveTick((t) => t + 1);
        }
      })();
      return group;
    },
    [materialId, mutate, reportQuestionRefs, fetchBullets, setBulletsPending, applySpecialPages]
  );

  // Regenerate a special slide's bullets, re-paginating its whole page group.
  const regenerateSpecial = useCallback(
    async (chart: ChartSpec) => {
      const type = chart.chart_type;
      // Themes charts (open-ended) just refresh their bullets in place.
      if (isThemes(chart)) {
        const ref = chart.question_ref;
        setBulletsPending(ref, true);
        try {
          const { bullets } = await api.materials.aiThemes(materialId, {
            question_ref: ref,
          });
          updateChartByRef(ref, { options: { ...(chart.options ?? {}), bullets } });
        } catch (e) {
          toast.error(`Could not regenerate themes: ${errMsg(e)}`);
        } finally {
          setBulletsPending(ref, false);
          setAiSaveTick((t) => t + 1);
        }
        return;
      }
      const group =
        (typeof chart.options?.group === "string" ? chart.options.group : null) ??
        chart.question_ref;
      const heading = (chart.slide_title || SPECIAL_HEADINGS[type] || "").replace(
        /\s*\(\d+\/\d+\)\s*$/,
        ""
      );
      setBulletsPending(group, true);
      try {
        if (type === "special_demographics") {
          const { bullets, charts } = await api.materials.aiDemographics(
            materialId,
            { question_refs: reportQuestionRefs() }
          );
          applyDemographics(group, heading, bullets, charts);
        } else {
          const bullets = await fetchBullets(type, reportQuestionRefs());
          applySpecialPages(group, type, heading, bullets);
        }
      } catch (e) {
        toast.error(`Could not regenerate slide: ${errMsg(e)}`);
      } finally {
        setBulletsPending(group, false);
        setAiSaveTick((t) => t + 1);
      }
    },
    [
      materialId,
      reportQuestionRefs,
      fetchBullets,
      setBulletsPending,
      applySpecialPages,
      updateChartByRef,
    ]
  );

  // Persist any unsaved edits before navigating; abort if the save fails
  // (save() already toasts on failure). Used by every exit/transition so
  // in-memory changes are never silently dropped.
  const commitThen = useCallback(
    async (action: () => void) => {
      if (dirty) {
        const ok = await save();
        if (!ok) return;
      }
      action();
    },
    [dirty, save]
  );

  function goNext() {
    commitThen(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)));
  }

  function goPrev() {
    commitThen(() => setStep((s) => Math.max(0, s - 1)));
  }

  // Inline report rename: update the draft (persisted on save), the workspace
  // listing, and flush to the backend.
  function commitName() {
    const next = nameDraft.trim();
    setEditingName(false);
    if (!next || next === draft?.name) return;
    mutate((d) => ({ ...d, name: next }));
    renameReport(reportId, next);
    setAiSaveTick((t) => t + 1); // persist via the post-commit save effect
  }

  // Self-heal a stale/deleted report id out of the workspace, once.
  const missingFired = useRef(false);
  useEffect(() => {
    if (isError && !missingFired.current) {
      missingFired.current = true;
      onMissing?.();
    }
  }, [isError, onMissing]);

  // Stale report id (404 after a backend restart / deletion elsewhere): show
  // an escapable error panel instead of trapping the user on a spinner.
  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-muted">
          <FileXIcon className="size-7 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold tracking-tight">
          Report unavailable
        </h3>
        <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted-foreground">
          This report couldn't be loaded. It may have been removed.
        </p>
        <Button className="mt-5" onClick={onClose}>
          <ChevronLeftIcon className="size-4" />
          Back to reports
        </Button>
      </div>
    );
  }

  if (isLoading || !draft) {
    return (
      <div className="flex items-center justify-center py-32 text-muted-foreground">
        <Loader2Icon className="size-5 animate-spin" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-5 flex items-center justify-between gap-4">
        <div className="min-w-0">
          {editingName ? (
            <div className="flex items-center gap-2">
              <Input
                autoFocus
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitName();
                  if (e.key === "Escape") setEditingName(false);
                }}
                className="h-9 max-w-sm text-base font-semibold"
              />
              <Button size="icon-sm" onClick={commitName}>
                <CheckIcon className="size-4" />
              </Button>
              <Button
                size="icon-sm"
                variant="ghost"
                onClick={() => setEditingName(false)}
              >
                <XIcon className="size-4" />
              </Button>
            </div>
          ) : (
            <div className="group flex items-center gap-2">
              <h2 className="truncate text-base font-semibold">{draft.name}</h2>
              <Button
                size="icon-sm"
                variant="ghost"
                className="text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
                onClick={() => {
                  setNameDraft(draft.name);
                  setEditingName(true);
                }}
                title="Rename report"
              >
                <PencilIcon className="size-4" />
              </Button>
            </div>
          )}
          {formatReportDate(createdAt) && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              Created {formatReportDate(createdAt)}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {dirty ? (
            <span className="text-xs text-muted-foreground">
              Unsaved changes
            </span>
          ) : savedAt ? (
            <span className="flex items-center gap-1 text-xs text-emerald-600">
              <CheckIcon className="size-3.5" /> Saved
            </span>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={save}
            disabled={updateReport.isPending}
          >
            {updateReport.isPending ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : (
              <SaveIcon className="size-4" />
            )}
            Save
          </Button>
        </div>
      </div>

      {/* Stepper + prev/next nav, with the phase instruction centered below */}
      <div className="mb-6 rounded-xl border bg-card px-3 py-2">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0"
            onClick={goPrev}
            disabled={step === 0}
          >
            <ArrowLeftIcon className="size-4" />
            Prev
          </Button>
          <div className="flex flex-1 justify-center">
            <Stepper
              current={step}
              onJump={(i) => commitThen(() => setStep(i))}
              chartCount={draft.charts.length}
            />
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0"
            onClick={goNext}
            disabled={step >= STEPS.length - 1}
          >
            Next
            <ArrowRightIcon className="size-4" />
          </Button>
        </div>
        {STEP_INSTRUCTIONS[step] && (
          <p className="mt-1.5 text-center text-xs text-muted-foreground">
            {STEP_INSTRUCTIONS[step]}
          </p>
        )}
      </div>

      {/* Step body */}
      <div className="min-h-[400px]">
        {step === 0 && (
          <StepSelect
            materialId={materialId}
            addedRefs={addedRefs}
            onToggle={toggleQuestion}
            onSelectMany={selectMany}
            grouping={draft.grouping ?? { groups: [], singles: [] }}
            onGroupingChange={(g) => mutate((d) => ({ ...d, grouping: g }))}
            onPruneRefs={pruneToValidRefs}
          />
        )}
        {step === 1 && (
          <StepConfigure
            materialId={materialId}
            charts={draft.charts}
            grouping={draft.grouping ?? { groups: [], singles: [] }}
            aiPending={aiPending}
            onUpdateChart={updateChart}
            onRemoveChart={removeChart}
            onReorder={reorderCharts}
            onEnsureTitles={ensureTitles}
            onAddSpecial={addSpecialSlide}
            onRegenerateSpecial={regenerateSpecial}
          />
        )}
        {step === 2 && (
          <StepDownload
            caseId={caseId}
            reportId={reportId}
            materialId={materialId}
            draft={draft}
            save={save}
          />
        )}
      </div>
    </div>
  );
}
