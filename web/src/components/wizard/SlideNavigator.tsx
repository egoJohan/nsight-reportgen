import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  GripVerticalIcon,
  LayoutGridIcon,
  PlusIcon,
  SearchIcon,
  Trash2Icon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { chartTypeLabel, isSpecialSlide, rendersFullSlide } from "@/lib/charts";
import { useChartPreview } from "@/lib/queries";
import { useDragReorder } from "@/lib/useDragReorder";
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
  onAddSlide,
  onRemove,
}: {
  charts: ChartSpec[];
  activeIndex: number;
  questionMap: Map<string, Question>;
  onSelect: (index: number) => void;
  onOpenOverview: () => void;
  onAddSlide?: () => void;
  onRemove?: () => void;
}) {
  const [jumpOpen, setJumpOpen] = useState(false);
  const total = charts.length;
  const cur = charts[activeIndex];
  if (!cur) return null;

  return (
    <div className="flex items-center gap-2 rounded-lg border bg-card p-1.5">
      <Button
        variant="outline"
        size="sm"
        disabled={activeIndex <= 0}
        onClick={() => onSelect(activeIndex - 1)}
      >
        <ChevronLeftIcon className="size-4" /> Prev
      </Button>

      <div className="relative min-w-0 flex-1">
        <button
          onClick={() => setJumpOpen((o) => !o)}
          className="flex w-full items-center gap-2 rounded-md border bg-background px-3 py-1.5 text-left hover:border-primary/50 hover:bg-accent/40"
        >
          <span className="shrink-0 text-xs font-semibold tabular-nums text-primary">
            {activeIndex + 1} / {total}
          </span>
          <span className="min-w-0 flex-1 truncate text-sm font-medium">
            {slideTitle(cur, questionMap)}
          </span>
          <span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">
            {chartTypeLabel(cur.chart_type)}
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
            onClose={() => setJumpOpen(false)}
          />
        )}
      </div>

      <Button
        variant="outline"
        size="sm"
        disabled={activeIndex >= total - 1}
        onClick={() => onSelect(activeIndex + 1)}
      >
        Next <ChevronRightIcon className="size-4" />
      </Button>
      <Button variant="outline" size="sm" onClick={onOpenOverview}>
        <LayoutGridIcon className="size-4" /> Overview
      </Button>
      {onAddSlide && (
        <Button variant="outline" size="sm" onClick={onAddSlide}>
          <PlusIcon className="size-4" /> Add slide
        </Button>
      )}
      {onRemove && (
        <Button
          variant="outline"
          size="sm"
          className="text-muted-foreground hover:text-destructive"
          title="Remove this slide"
          onClick={onRemove}
        >
          <Trash2Icon className="size-4" />
        </Button>
      )}
    </div>
  );
}

// ── Type-to-jump popover ──────────────────────────────────────────────────────
function JumpPopover({
  charts,
  questionMap,
  activeIndex,
  onPick,
  onClose,
}: {
  charts: ChartSpec[];
  questionMap: Map<string, Question>;
  activeIndex: number;
  onPick: (index: number) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

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
    <div
      ref={ref}
      className="absolute inset-x-0 top-full z-30 mt-1 overflow-hidden rounded-lg border bg-popover shadow-lg"
    >
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
  onReorder,
  onAddSlide,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  charts: ChartSpec[];
  materialId: string;
  grouping: GroupingOverride;
  questionMap: Map<string, Question>;
  activeRef: string | null;
  onSelect: (index: number) => void;
  onReorder?: (from: number, to: number) => void;
  onAddSlide?: () => void;
}) {
  const { dragIndex, overIndex, containerRef, itemProps } = useDragReorder(onReorder);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[88vh] w-[92vw] max-w-[92vw] flex-col gap-3 sm:max-w-[92vw]">
        <div className="flex items-center justify-between">
          <DialogTitle>All slides ({charts.length})</DialogTitle>
          {onAddSlide && (
            <Button variant="outline" size="sm" onClick={onAddSlide}>
              <PlusIcon className="size-4" /> Add slide
            </Button>
          )}
        </div>
        <div
          ref={containerRef as React.RefObject<HTMLDivElement>}
          className="grid min-h-0 flex-1 grid-cols-2 gap-3 overflow-y-auto p-1 sm:grid-cols-3 lg:grid-cols-4"
        >
          {charts.map((c, i) => (
            <SlideThumb
              key={`${c.question_ref}-${i}`}
              materialId={materialId}
              chart={c}
              index={i}
              isActive={c.question_ref === activeRef}
              grouping={grouping}
              questionMap={questionMap}
              dragging={dragIndex === i}
              dropTarget={dragIndex !== null && overIndex === i && dragIndex !== i}
              itemProps={itemProps(i)}
              onClick={() => {
                onSelect(i);
                onOpenChange(false);
              }}
            />
          ))}
        </div>
      </DialogContent>
    </Dialog>
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
  dragging,
  dropTarget,
  itemProps,
  onClick,
}: {
  materialId: string;
  chart: ChartSpec;
  index: number;
  isActive: boolean;
  grouping: GroupingOverride;
  questionMap: Map<string, Question>;
  dragging: boolean;
  dropTarget: boolean;
  itemProps: Record<string, unknown>;
  onClick: () => void;
}) {
  // renderTitle MUST match DeckPrefetch (rendersFullSlide) so this reuses the warmed cache.
  const { data: url } = useChartPreview(materialId, chart, {
    renderTitle: rendersFullSlide(chart),
    grouping,
  });

  return (
    <div
      {...itemProps}
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-lg border bg-card transition-colors",
        isActive
          ? "border-primary ring-1 ring-primary"
          : "border-border hover:border-primary/40",
        dragging && "opacity-40",
        dropTarget && "ring-2 ring-primary"
      )}
    >
      <span className="absolute left-1.5 top-1.5 z-10 flex size-5 items-center justify-center rounded bg-background/85 text-xs tabular-nums shadow-sm">
        {index + 1}
      </span>
      <span
        className="absolute right-1.5 top-1.5 z-10 cursor-grab text-muted-foreground/50 opacity-0 transition-opacity group-hover:opacity-100"
        title="Drag to reorder"
      >
        <GripVerticalIcon className="size-4" />
      </span>
      <button onClick={onClick} className="flex flex-1 flex-col text-left">
        <div className="flex aspect-[4/3] items-center justify-center overflow-hidden bg-muted/30">
          {url ? (
            <img src={url} alt="" className="h-full w-full object-contain" />
          ) : (
            <span className="text-xs text-muted-foreground">
              {chartTypeLabel(chart.chart_type)}
            </span>
          )}
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
