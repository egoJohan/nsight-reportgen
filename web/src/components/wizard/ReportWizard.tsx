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
import type { ChartSpec, Question, ReportDoc } from "@/lib/api";
import { useReport, useUpdateReport } from "@/lib/queries";
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
  { id: "configure", label: "Configure" },
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
  const updateReport = useUpdateReport(caseId);

  const [draft, setDraft] = useState<ReportDoc | null>(null);
  const [step, setStep] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

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

  const addCharts = useCallback(
    (questions: Question[]) => {
      mutate((d) => {
        const existing = new Set(d.charts.map((c) => c.question_ref));
        const fresh: ChartSpec[] = questions
          .filter((q) => !existing.has(q.qid))
          .map((q) => makeChart(q.qid, q.suggested_chart_type));
        return {
          ...d,
          charts: normalizeSlots([...d.charts, ...fresh]),
        };
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
            onAdd={(qs) => {
              addCharts(qs);
              setStep(1);
            }}
          />
        )}
        {step === 1 && (
          <StepConfigure
            materialId={materialId}
            charts={draft.charts}
            onUpdateChart={updateChart}
            onRemoveChart={removeChart}
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
