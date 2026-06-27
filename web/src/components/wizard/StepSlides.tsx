import { useMemo } from "react";
import { ArrowDownIcon, ArrowUpIcon, BarChart3Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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

  const questionMap = useMemo(() => {
    const m = new Map<string, Question>();
    (questions ?? []).forEach((q) => m.set(q.qid, q));
    return m;
  }, [questions]);

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
      <div>
        <h3 className="text-base font-semibold">Slides</h3>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Set a title and description for each slide, and order them with the
          arrows. Titles default to the question text.
        </p>
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
                  <Label className="text-xs font-medium text-muted-foreground">
                    Slide title
                  </Label>
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
