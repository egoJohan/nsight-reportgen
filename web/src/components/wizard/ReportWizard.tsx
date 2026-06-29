import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckIcon,
  ChevronLeftIcon,
  FileXIcon,
  Loader2Icon,
  SaveIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { ChartSpec, Question, ReportDoc } from "@/lib/api";
import { useQuestions, useReport, useUpdateReport } from "@/lib/queries";
import { makeChart, normalizeSlots } from "@/lib/charts";
import StepSelect from "./StepSelect";
import StepConfigure from "./StepConfigure";
import StepReview from "./StepReview";
import StepSlides from "./StepSlides";
import StepDownload from "./StepDownload";

/** Move an item within an array, returning a new array. */
function move<T>(arr: T[], from: number, to: number): T[] {
  if (to < 0 || to >= arr.length || from === to) return arr;
  const next = arr.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

const STEPS = [
  { id: "select", label: "Select" },
  { id: "configure", label: "Design" },
  { id: "review", label: "Review" },
  { id: "slides", label: "Slides" },
  { id: "download", label: "Download" },
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
        // All steps reachable; Download requires at least one chart.
        const reachable = i < 4 || chartCount > 0;
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
  const { data: questions } = useQuestions(materialId);
  const updateReport = useUpdateReport(caseId);

  const [draft, setDraft] = useState<ReportDoc | null>(null);
  const [step, setStep] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  // Per-chart pending flags (keyed by question_ref) so the Configure preview
  // can show "Generating title…" / "Shortening labels…" placeholders over the
  // regions that are still being produced. Set true when a chart's AI call
  // starts, false when it resolves/fails.
  const [aiPending, setAiPending] = useState<
    Record<string, { titlePending: boolean; labelsPending: boolean }>
  >({});

  // Initialise the working draft once the report loads.
  useEffect(() => {
    if (loaded && !draft) {
      setDraft({
        name: loaded.name,
        render_mode: "image",
        template_ref: loaded.template_ref ?? "",
        charts: loaded.charts ?? [],
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

  // Enabling/disabling a question directly edits the report: add its chart when
  // absent, remove it when present (no separate "Add selected" step).
  const toggleQuestion = useCallback(
    (q: Question) => {
      mutate((d) => {
        const exists = d.charts.some((c) => c.question_ref === q.qid);
        const charts = exists
          ? d.charts.filter((c) => c.question_ref !== q.qid)
          : [...d.charts, makeChart(q.qid, q.suggested_chart_type)];
        return { ...d, charts: normalizeSlots(charts) };
      });
    },
    [mutate]
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

  // ── Auto AI-formatting (the default, not a manual click) ──────────────────
  // When charts are added (or a report loads without them), automatically
  // short-label every chart's categories and generate a descriptive slide
  // title, then store the results onto the specs so Configure shows SHORT
  // labels and Slides shows the AI title by default. Per-chart graceful
  // fallback to the originals on failure; never retried within a session.
  const aiRunning = useRef(false);
  const titlesAttempted = useRef<Set<string>>(new Set());
  // Bumped when an auto-format pass finishes; a separate effect then persists
  // the result. Saving from a post-commit effect (instead of inline) ensures
  // every generated patch has flushed into the draft before we read it.
  const [aiSaveTick, setAiSaveTick] = useState(0);

  useEffect(() => {
    // Wait for questions so we only request labels for charts that have
    // category labels (and compute label + title work in one pass).
    if (!draft || !questions || aiRunning.current) return;

    const qMap = new Map<string, Question>();
    questions.forEach((q) => qMap.set(q.qid, q));

    // Category labels are NOT auto-shortened — the cleaned option labels are the
    // default, and AI shortening is opt-in via the "Shorten with AI" button in
    // the label editor. We only auto-generate the descriptive slide title.
    type Task = { ref: string };
    const tasks: Task[] = [];
    for (const c of draft.charts) {
      const needTitle =
        !titlesAttempted.current.has(c.question_ref) && !c.slide_title;
      if (needTitle) tasks.push({ ref: c.question_ref });
    }
    if (tasks.length === 0) return;

    aiRunning.current = true;
    // Mark the title region pending up front so the preview shows the
    // "Generating title…" placeholder immediately.
    setAiPending((prev) => {
      const next = { ...prev };
      for (const t of tasks) {
        next[t.ref] = { titlePending: true, labelsPending: false };
      }
      return next;
    });

    const clearPending = (ref: string) =>
      setAiPending((prev) => ({
        ...prev,
        [ref]: { ...prev[ref], titlePending: false },
      }));

    // Per-chart worker: generate the descriptive slide title.
    const worker = async (task: Task) => {
      titlesAttempted.current.add(task.ref);
      const chart = draftRef.current?.charts.find(
        (c) => c.question_ref === task.ref
      );
      const jobs: Promise<unknown>[] = [
        api.materials
          .aiSlideTitle(materialId, {
            question_ref: task.ref,
            statistic: chart?.statistic,
            classifying_var: chart?.classifying_var,
            show_not_answered: chart?.show_not_answered,
            not_answered_codes: chart?.not_answered_codes,
          })
          .then(({ title }) => {
            if (title) updateChartByRef(task.ref, { slide_title: title });
          })
          .catch(() => {
            /* graceful: fall back to the question text */
          })
          .finally(() => clearPending(task.ref)),
      ];
      await Promise.allSettled(jobs);
    };

    // Limited concurrency (≈3 charts in flight); egoHive is slow.
    const run = async () => {
      let idx = 0;
      const lanes = Array.from(
        { length: Math.min(3, tasks.length) },
        async () => {
          while (idx < tasks.length) {
            const t = tasks[idx++];
            await worker(t);
          }
        }
      );
      await Promise.all(lanes);
    };

    run().finally(() => {
      aiRunning.current = false;
      // Persist via the effect below, after the patches have committed.
      setAiSaveTick((t) => t + 1);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, questions, materialId, updateChartByRef]);

  // Persist generated overrides/titles once an auto-format pass settles. Runs
  // post-commit so draftRef already reflects every generated patch.
  useEffect(() => {
    if (aiSaveTick === 0) return;
    void save();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aiSaveTick]);

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
        <div className="flex min-w-0 items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            className="-ml-2 shrink-0 text-muted-foreground"
            onClick={() => commitThen(onClose)}
          >
            <ChevronLeftIcon className="size-4" />
            Back to reports
          </Button>
          <Separator orientation="vertical" className="h-5" />
          <h2 className="truncate text-base font-semibold">{draft.name}</h2>
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

      {/* Stepper */}
      <div className="mb-6 flex justify-center rounded-xl border bg-card px-3 py-2">
        <Stepper
          current={step}
          onJump={(i) => commitThen(() => setStep(i))}
          chartCount={draft.charts.length}
        />
      </div>

      {/* Step body */}
      <div className="min-h-[400px]">
        {step === 0 && (
          <StepSelect
            materialId={materialId}
            addedRefs={addedRefs}
            onToggle={toggleQuestion}
          />
        )}
        {step === 1 && (
          <StepConfigure
            materialId={materialId}
            charts={draft.charts}
            aiPending={aiPending}
            onUpdateChart={updateChart}
            onRemoveChart={removeChart}
            onReorder={reorderCharts}
          />
        )}
        {step === 2 && (
          <StepReview
            materialId={materialId}
            charts={draft.charts}
            onBack={() => setStep(1)}
          />
        )}
        {step === 3 && (
          <StepSlides
            materialId={materialId}
            charts={draft.charts}
            onUpdateChart={updateChart}
            onReorder={reorderCharts}
          />
        )}
        {step === 4 && (
          <StepDownload
            caseId={caseId}
            reportId={reportId}
            materialId={materialId}
            draft={draft}
            save={save}
          />
        )}
      </div>

      {/* Footer nav */}
      <div className="mt-6 flex items-center justify-between border-t pt-4">
        <Button
          variant="ghost"
          onClick={() => commitThen(() => setStep((s) => Math.max(0, s - 1)))}
          disabled={step === 0}
        >
          <ArrowLeftIcon className="size-4" />
          Back
        </Button>
        <Button onClick={goNext} disabled={step >= STEPS.length - 1}>
          Next
          <ArrowRightIcon className="size-4" />
        </Button>
      </div>
    </div>
  );
}
