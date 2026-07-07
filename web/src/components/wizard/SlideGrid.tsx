import { cn } from "@/lib/utils";
import { chartTypeLabel, isSpecialSlide, SLIDE_ASPECT } from "@/lib/charts";
import { useChartPreview } from "@/lib/queries";
import type { ChartSpec, GroupingOverride, Question } from "@/lib/api";

/** The display title for a slide: a question's text, or a special slide's heading. */
export function slideTitle(c: ChartSpec, questionMap: Map<string, Question>): string {
  if (isSpecialSlide(c)) return c.slide_title || chartTypeLabel(c.chart_type);
  return questionMap.get(c.question_ref)?.text ?? c.question_ref;
}

// ── All-slides grid (used by the Preview step) ───────────────────────────────
// Navigate-only: reordering + adding slides live in the Select step; clicking a
// thumbnail just selects that slide (index).
export function SlideGrid({
  charts,
  materialId,
  grouping,
  questionMap,
  activeRef,
  onSelect,
}: {
  charts: ChartSpec[];
  materialId: string;
  grouping: GroupingOverride;
  questionMap: Map<string, Question>;
  activeRef: string | null;
  onSelect: (index: number) => void;
}) {
  return (
    <div className="grid auto-rows-max grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {charts.map((c, i) => (
        <SlideThumb
          key={`${c.question_ref}-${i}`}
          materialId={materialId}
          chart={c}
          index={i}
          isActive={c.question_ref === activeRef}
          grouping={grouping}
          questionMap={questionMap}
          onClick={() => onSelect(i)}
        />
      ))}
    </div>
  );
}

// ── One thumbnail (calls useChartPreview → hits DeckPrefetch's warm cache) ──────
function SlideThumb({
  materialId,
  chart,
  index,
  isActive,
  grouping,
  questionMap,
  onClick,
}: {
  materialId: string;
  chart: ChartSpec;
  index: number;
  isActive: boolean;
  grouping: GroupingOverride;
  questionMap: Map<string, Question>;
  onClick: () => void;
}) {
  // renderTitle:true shows the FULL slide (title baked in), so the grid faithfully
  // reflects the deck. MUST match DeckPrefetch's renderTitle to reuse its warm cache.
  const { data: url } = useChartPreview(materialId, chart, {
    renderTitle: true,
    grouping,
  });

  return (
    <div
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-lg border bg-card transition-colors",
        isActive
          ? "border-primary ring-1 ring-primary"
          : "border-border hover:border-primary/40"
      )}
    >
      <button onClick={onClick} className="flex flex-1 flex-col text-left">
        {/* Same box as the Design preview (relative aspect box + absolutely
            positioned filling image) so the slide keeps its exact proportions and
            charts aren't stretched. */}
        <div className={`relative w-full overflow-hidden bg-muted/30 ${SLIDE_ASPECT}`}>
          {url ? (
            <img src={url} alt="" className="absolute inset-0 size-full object-contain" />
          ) : (
            <span className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
              {chartTypeLabel(chart.chart_type)}
            </span>
          )}
          <span className="absolute bottom-1.5 right-1.5 z-10 flex size-5 items-center justify-center rounded bg-background/85 text-xs tabular-nums shadow-sm">
            {index + 1}
          </span>
        </div>
        <div className="border-t p-2">
          <p className="line-clamp-2 text-xs leading-snug">{slideTitle(chart, questionMap)}</p>
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            {chartTypeLabel(chart.chart_type)}
          </p>
        </div>
      </button>
    </div>
  );
}
