import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  LayoutGridIcon,
  InfoIcon,
  SearchIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { chartTypeLabel, isSpecialSlide, SLIDE_ASPECT } from "@/lib/charts";
import { useChartPreview } from "@/lib/queries";
import type { ChartSpec, GroupingOverride, Question } from "@/lib/api";

/** The display title for a slide: a question's text, or a special slide's heading. */
export function slideTitle(c: ChartSpec, questionMap: Map<string, Question>): string {
  if (isSpecialSlide(c)) return c.slide_title || chartTypeLabel(c.chart_type);
  return questionMap.get(c.question_ref)?.text ?? c.question_ref;
}

// ── Navigator bar ───────────────────────────────────────────────────────────
export function SlideNavigator({
  charts,
  activeIndex,
  questionMap,
  onSelect,
  onOpenOverview,
  onEditQuestion,
}: {
  charts: ChartSpec[];
  activeIndex: number;
  questionMap: Map<string, Question>;
  onSelect: (index: number) => void;
  onOpenOverview: () => void;
  onEditQuestion?: (qid: string) => void;
}) {
  const [jumpOpen, setJumpOpen] = useState(false);
  const jumpRef = useRef<HTMLDivElement>(null);
  const total = charts.length;
  const cur = charts[activeIndex];

  // Close the jump popover on an outside click / Esc. The trigger button lives INSIDE
  // jumpRef, so clicking it again just toggles (no close-then-reopen flicker).
  useEffect(() => {
    if (!jumpOpen) return;
    function onDown(e: MouseEvent) {
      if (jumpRef.current && !jumpRef.current.contains(e.target as Node)) setJumpOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setJumpOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [jumpOpen]);

  if (!cur) return null;

  return (
    <div className="flex items-center gap-2 rounded-lg border bg-card p-1.5">
      <Button
        variant="outline"
        size="icon-lg"
        disabled={activeIndex <= 0}
        title="Previous slide (←)"
        onClick={() => onSelect(activeIndex - 1)}
      >
        <ChevronLeftIcon className="size-4" />
      </Button>

      <div ref={jumpRef} className="relative min-w-0 flex-1">
        <button
          onClick={() => setJumpOpen((o) => !o)}
          className="flex h-9 w-full items-center gap-2 rounded-md border bg-background px-3 text-left hover:border-primary/50 hover:bg-accent/40"
        >
          <span className="shrink-0 text-xs font-semibold tabular-nums text-primary">
            {activeIndex + 1} / {total}
          </span>
          <span className="min-w-0 flex-1 truncate text-sm font-medium">
            {slideTitle(cur, questionMap)}
          </span>
          <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground" />
        </button>
        {jumpOpen && (
          <JumpPopover
            charts={charts}
            questionMap={questionMap}
            activeIndex={activeIndex}
            onPick={(i) => {
              onSelect(i);
              setJumpOpen(false);
            }}
          />
        )}
      </div>

      <Button
        variant="outline"
        size="icon-lg"
        disabled={activeIndex >= total - 1}
        title="Next slide (→)"
        onClick={() => onSelect(activeIndex + 1)}
      >
        <ChevronRightIcon className="size-4" />
      </Button>
      {onEditQuestion && !isSpecialSlide(cur) && (
        <Button
          variant="outline"
          size="icon-lg"
          title="View question details"
          onClick={() => onEditQuestion(cur.question_ref)}
        >
          <InfoIcon className="size-4" />
        </Button>
      )}
      <Button
        variant="outline"
        size="icon-lg"
        title="Overview — all slides"
        onClick={onOpenOverview}
      >
        <LayoutGridIcon className="size-4" />
      </Button>
    </div>
  );
}

// ── Type-to-jump popover ──────────────────────────────────────────────────────
function JumpPopover({
  charts,
  questionMap,
  activeIndex,
  onPick,
}: {
  charts: ChartSpec[];
  questionMap: Map<string, Question>;
  activeIndex: number;
  onPick: (index: number) => void;
}) {
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return charts
      .map((c, i) => ({ c, i }))
      .filter(
        ({ c }) =>
          !needle ||
          slideTitle(c, questionMap).toLowerCase().includes(needle) ||
          chartTypeLabel(c.chart_type).toLowerCase().includes(needle)
      );
  }, [q, charts, questionMap]);

  return (
    <div className="absolute inset-x-0 top-full z-30 mt-1 overflow-hidden rounded-lg border bg-popover shadow-lg">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <SearchIcon className="size-4 text-muted-foreground" />
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && filtered[0]) onPick(filtered[0].i);
          }}
          placeholder="Jump to slide… (question or chart type)"
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>
      <div className="max-h-72 overflow-y-auto p-1">
        {filtered.length === 0 ? (
          <p className="px-2 py-4 text-center text-xs text-muted-foreground">No slides match</p>
        ) : (
          filtered.map(({ c, i }) => (
            <button
              key={`${c.question_ref}-${i}`}
              onClick={() => onPick(i)}
              className={cn(
                "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent",
                i === activeIndex && "bg-primary/5"
              )}
            >
              <span className="flex size-5 shrink-0 items-center justify-center rounded bg-muted text-xs tabular-nums text-muted-foreground">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1 truncate">{slideTitle(c, questionMap)}</span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {chartTypeLabel(c.chart_type)}
              </span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

// ── Full-screen Overview grid ─────────────────────────────────────────────────
export function SlideOverview({
  open,
  onOpenChange,
  charts,
  materialId,
  grouping,
  questionMap,
  activeRef,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  charts: ChartSpec[];
  materialId: string;
  grouping: GroupingOverride;
  questionMap: Map<string, Question>;
  activeRef: string | null;
  onSelect: (index: number) => void;
}) {
  // Navigate-only: reordering + adding slides live in the Select step (this deck
  // grid just jumps to a slide). See StepSelect's DeckList.
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[88vh] w-[92vw] max-w-[92vw] flex-col gap-3 sm:max-w-[92vw]">
        <div className="flex items-center justify-between">
          <DialogTitle>All slides ({charts.length})</DialogTitle>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-1">
          <SlideGrid
            charts={charts}
            materialId={materialId}
            grouping={grouping}
            questionMap={questionMap}
            activeRef={activeRef}
            onSelect={(i) => {
              onSelect(i);
              onOpenChange(false);
            }}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── All-slides grid (reused by the Preview step; also wrapped by SlideOverview) ─
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

// ── One overview thumbnail (calls useChartPreview → hits DeckPrefetch's cache) ──
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
