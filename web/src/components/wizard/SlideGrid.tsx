import { cn } from "@/lib/utils";
import { chartTypeLabel, SLIDE_ASPECT } from "@/lib/charts";
import { useChartPreview } from "@/lib/queries";
import SlideTitleOverlay from "@/components/wizard/SlideTitleOverlay";
import type { ChartSpec, GroupingOverride, Question } from "@/lib/api";
import { slideTitle } from "@/components/wizard/slideTitle";

/** The display title for a slide: a question's text, or a special slide's heading. */

// ── All-slides grid (used by the Preview step) ───────────────────────────────
// Navigate-only: reordering + adding slides live in the Select step; clicking a
// thumbnail just selects that slide (index).
export function SlideGrid({
  charts,
  materialId,
  reportId,
  templateRef,
  grouping,
  questionMap,
  activeRef,
  onSelect,
}: {
  charts: ChartSpec[];
  materialId: string;
  // Which report (and its own template choice) these previews are for — see
  // SlideThumb. Optional only so a caller mid-migration doesn't have to know
  // about this; every current caller has both.
  reportId?: string;
  templateRef?: string;
  grouping: GroupingOverride;
  questionMap: Map<string, Question>;
  // The active slide's slide_id (question_ref is not unique across slides).
  activeRef: string | null;
  onSelect: (index: number) => void;
}) {
  return (
    <div className="grid auto-rows-max grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {charts.map((c, i) => (
        <SlideThumb
          key={`${c.question_ref}-${i}`}
          materialId={materialId}
          reportId={reportId}
          templateRef={templateRef}
          chart={c}
          index={i}
          isActive={c.slide_id === activeRef}
          grouping={grouping}
          questionMap={questionMap}
          onClick={() => onSelect(i)}
        />
      ))}
    </div>
  );
}

// ── One thumbnail ─────────────────────────────────────────────────────────
function SlideThumb({
  materialId,
  reportId,
  templateRef,
  chart,
  index,
  isActive,
  grouping,
  questionMap,
  onClick,
}: {
  materialId: string;
  reportId?: string;
  templateRef?: string;
  chart: ChartSpec;
  index: number;
  isActive: boolean;
  grouping: GroupingOverride;
  questionMap: Map<string, Question>;
  onClick: () => void;
}) {
  // renderTitle:true — the SAME variant the Design step renders and prefetches
  // for every slide (StepConfigure's DeckPrefetch). `renderTitle` is part of the
  // preview cache key, so asking for the other variant here meant the grid could
  // not reuse a single one of those renders: every slide was a cache miss and the
  // whole deck rendered a second time on the way into Preview. It also meant no
  // title, because the fast composited path deliberately leaves the title band to
  // the frontend and only emits `titleMeta` for it when a template resolves.
  // Baking the title in is WYSIWYG against the deck anyway, and costs nothing
  // extra now that both steps share one variant. (DeckPrefetch's own comment has
  // always said this variant serves "BOTH the Design preview and the Overview
  // grid" — the grid just never asked for it.)
  const { data } = useChartPreview(materialId, chart, {
    renderTitle: true,
    grouping,
    reportId,
    templateRef,
  });
  const url = data?.dataUrl;
  const titleMeta = data?.titleMeta;

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
            charts aren't stretched. The aspect ratio itself follows the template's
            own (X-Slide-Aspect) when known, so the image fills the box exactly and
            the title overlay's percentage-based box lines up with it — otherwise
            `object-contain` can letterbox a non-16:9 template inside this box and
            the two would no longer agree on where "the box" is. */}
        <div
          className={`relative w-full overflow-hidden bg-muted/30 ${SLIDE_ASPECT}`}
          style={titleMeta ? { aspectRatio: titleMeta.aspect } : undefined}
        >
          {url ? (
            <img src={url} alt="" className="absolute inset-0 size-full object-contain" />
          ) : (
            <span className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
              {chartTypeLabel(chart.chart_type)}
            </span>
          )}
          <SlideTitleOverlay title={chart.slide_title} meta={titleMeta} />
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
