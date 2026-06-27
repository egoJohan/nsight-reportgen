import { useMemo, useState } from "react";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  BarChart3Icon,
  Loader2Icon,
  SparklesIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { ChartSpec, Question } from "@/lib/api";
import { useQuestions } from "@/lib/queries";
import { chartTypeLabel } from "@/lib/charts";
import ChartThumb from "./ChartThumb";

export default function StepSlides({
  materialId,
  charts,
  onUpdateChart,
  onReorder,
}: {
  materialId: string;
  charts: ChartSpec[];
  onUpdateChart: (index: number, patch: Partial<ChartSpec>) => void;
  onReorder: (from: number, to: number) => void;
}) {
  const { data: questions } = useQuestions(materialId);

  // Indices currently generating a title (per-row spinners).
  const [generating, setGenerating] = useState<Set<number>>(new Set());
  const [generatingAll, setGeneratingAll] = useState(false);

  const questionMap = useMemo(() => {
    const m = new Map<string, Question>();
    (questions ?? []).forEach((q) => m.set(q.qid, q));
    return m;
  }, [questions]);

  // Generate a title for one slide via egoHive; returns the title or null.
  const generateTitle = async (index: number): Promise<string | null> => {
    const chart = charts[index];
    setGenerating((prev) => new Set(prev).add(index));
    try {
      const { title } = await api.materials.aiSlideTitle(materialId, {
        question_ref: chart.question_ref,
        statistic: chart.statistic,
        classifying_var: chart.classifying_var,
        show_not_answered: chart.show_not_answered,
        not_answered_codes: chart.not_answered_codes,
      });
      onUpdateChart(index, { slide_title: title });
      return title;
    } catch (e) {
      toast.error(
        `Title generation failed: ${
          e instanceof Error ? e.message : "unknown error"
        }`
      );
      return null;
    } finally {
      setGenerating((prev) => {
        const next = new Set(prev);
        next.delete(index);
        return next;
      });
    }
  };

  // Sequentially generate titles for every slide without one yet (egoHive is
  // slow — never fire N calls at once).
  const generateAll = async () => {
    setGeneratingAll(true);
    let made = 0;
    try {
      for (let i = 0; i < charts.length; i++) {
        if (charts[i].slide_title) continue;
        const title = await generateTitle(i);
        if (title) made++;
      }
      if (made > 0) toast.success(`Generated ${made} title(s)`);
    } finally {
      setGeneratingAll(false);
    }
  };

  if (charts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-24 text-center">
        <BarChart3Icon className="mb-3 size-8 text-muted-foreground/50" />
        <p className="text-sm font-medium">No slides yet</p>
        <p className="mt-1 max-w-xs text-sm text-muted-foreground">
          Add and configure charts first — each chart becomes a slide here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold">Slides</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Each title is AI-generated to describe its chart and stays fully
            editable. Order slides with the arrows.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          disabled={generatingAll}
          onClick={generateAll}
        >
          {generatingAll ? (
            <Loader2Icon className="size-4 animate-spin" />
          ) : (
            <SparklesIcon className="size-4" />
          )}
          {generatingAll ? "Generating titles…" : "Generate all titles"}
        </Button>
      </div>

      <div className="space-y-3">
        {charts.map((chart, i) => {
          const q = questionMap.get(chart.question_ref);
          const questionText = q?.text ?? chart.question_ref;
          return (
            <div
              key={`${chart.question_ref}-${i}`}
              className="grid grid-cols-[auto_180px_minmax(0,1fr)_auto] items-start gap-4 rounded-xl border bg-card p-4"
            >
              {/* Slide number */}
              <span className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-sm font-medium tabular-nums text-primary">
                {i + 1}
              </span>

              {/* Thumbnail */}
              <ChartThumb
                materialId={materialId}
                chart={chart}
                className="h-[130px]"
              />

              {/* Title + description */}
              <div className="min-w-0 space-y-3">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Label className="text-xs font-medium text-muted-foreground">
                      Slide title
                    </Label>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-xs text-muted-foreground"
                      disabled={generating.has(i) || generatingAll}
                      onClick={() => generateTitle(i)}
                    >
                      {generating.has(i) ? (
                        <Loader2Icon className="size-3.5 animate-spin" />
                      ) : (
                        <SparklesIcon className="size-3.5" />
                      )}
                      {chart.slide_title ? "Regenerate" : "Generate title"}
                    </Button>
                  </div>
                  <Input
                    value={chart.slide_title ?? ""}
                    placeholder={questionText}
                    onChange={(e) =>
                      onUpdateChart(i, {
                        slide_title: e.target.value.trim()
                          ? e.target.value
                          : null,
                      })
                    }
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">
                    Slide description
                  </Label>
                  <Textarea
                    value={chart.slide_description ?? ""}
                    placeholder="Optional subtitle shown under the title…"
                    rows={2}
                    onChange={(e) =>
                      onUpdateChart(i, {
                        slide_description: e.target.value.trim()
                          ? e.target.value
                          : null,
                      })
                    }
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  {chartTypeLabel(chart.chart_type)}
                </p>
              </div>

              {/* Reorder controls */}
              <div className="flex shrink-0 flex-col gap-1.5">
                <Button
                  variant="outline"
                  size="icon"
                  className="size-8"
                  disabled={i === 0}
                  onClick={() => onReorder(i, i - 1)}
                  aria-label="Move slide up"
                >
                  <ArrowUpIcon className="size-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="size-8"
                  disabled={i === charts.length - 1}
                  onClick={() => onReorder(i, i + 1)}
                  aria-label="Move slide down"
                >
                  <ArrowDownIcon className="size-4" />
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
