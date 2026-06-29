import { useMemo } from "react";
import { ArrowLeftIcon, BarChart3Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ChartSpec, Question } from "@/lib/api";
import { useQuestions } from "@/lib/queries";
import { chartTypeLabel } from "@/lib/charts";
import ChartThumb from "./ChartThumb";

export default function StepReview({
  materialId,
  charts,
  onBack,
}: {
  materialId: string;
  charts: ChartSpec[];
  onBack: () => void;
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
        <p className="text-sm font-medium">No charts to review</p>
        <p className="mt-1 max-w-xs text-sm text-muted-foreground">
          Go back to <span className="font-medium">Select</span> and add
          questions, then configure their charts.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold">
            Review — {charts.length} {charts.length === 1 ? "chart" : "charts"}
          </h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            A final look at every chart before you assemble the deck.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onBack}>
          <ArrowLeftIcon className="size-4" />
          Back to Design
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {charts.map((chart, i) => {
          const q = questionMap.get(chart.question_ref);
          return (
            <div
              key={`${chart.question_ref}-${i}`}
              className="flex flex-col overflow-hidden rounded-xl border bg-card"
            >
              <ChartThumb
                materialId={materialId}
                chart={chart}
                className="h-[240px] rounded-none border-0 border-b"
              />
              <div className="flex items-start gap-3 px-4 py-3">
                <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md bg-muted text-xs font-medium tabular-nums text-muted-foreground">
                  {i + 1}
                </span>
                <div className="min-w-0">
                  <p className="line-clamp-2 text-sm leading-snug font-medium">
                    {chart.slide_title || q?.text || chart.question_ref}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {chartTypeLabel(chart.chart_type)}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
