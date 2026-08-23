import { useEffect, useRef, useState } from "react";
import { AlertCircleIcon, ImageIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChartSpec, GroupingOverride } from "@/lib/api";
import { useChartPreview } from "@/lib/queries";
import * as previewQueue from "@/lib/previewQueue";

/**
 * A cached chart preview thumbnail. Backed by the shared useChartPreview cache,
 * so a given chart's preview is formed ONCE and reused across steps/mounts —
 * revisiting Review/Slides no longer re-renders every thumbnail.
 *
 * Rendering is LAZY: the (expensive, LibreOffice-backed) preview is requested
 * only once the thumbnail scrolls near the viewport, so a long report no longer
 * fires one render per slide on entry — only the handful of visible slides
 * render, the rest on demand as you scroll. Already-formed previews stay cached.
 */
export default function ChartThumb({
  materialId,
  chart,
  className,
  renderTitle,
  grouping,
  reportId,
  templateRef,
}: {
  materialId: string;
  chart: ChartSpec;
  className?: string;
  // Fast (composited, no LibreOffice) by default: the title is drawn in DOM
  // below over the image instead of baked into the PNG. A caller that needs
  // the exact baked slide (WYSIWYG against the deck) passes renderTitle: true.
  renderTitle?: boolean;
  grouping?: GroupingOverride;
  // Which report (and its own template choice) this is a preview for — see
  // SlideGrid.tsx's SlideThumb for why both matter.
  reportId?: string;
  templateRef?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (seen) return;
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setSeen(true);
          io.disconnect();
        }
      },
      { rootMargin: "300px" } // start rendering just before it scrolls into view
    );
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);

  // Scrolling a thumbnail into view moves its slide up the queue rather than
  // starting a render of its own — the queue is what decides that a headline is
  // written before a picture is drawn, and a component that fetched on its own
  // would render the slide once without its title and again with it.
  const slideId = chart.slide_id ?? "";
  useEffect(() => {
    if (seen && slideId) previewQueue.promote(slideId);
  }, [seen, slideId]);

  const { data, error, isFetching } = useChartPreview(materialId, chart, {
    renderTitle,
    grouping,
    reportId,
    templateRef,
  });
  const url = data?.dataUrl;
  const titleMeta = data?.titleMeta;
  const message =
    error instanceof Error ? error.message : error ? "Preview failed" : null;

  return (
    <div
      ref={ref}
      className={cn(
        "relative flex w-full items-center justify-center overflow-hidden rounded-lg border bg-muted/30 p-3",
        className
      )}
    >
      {url ? (
        // With a title box to draw (the fast path), the frame takes the
        // template's own aspect ratio and fills the available width so
        // `object-contain` never letterboxes it — otherwise the overlay's
        // percentage box and the image's actual rendered box would disagree
        // about where "the box" is. Without one (renderTitle:true, no overlay
        // to align), the image keeps its old free-scaling box.
        <div
          className="relative max-h-full max-w-full"
          style={titleMeta ? { aspectRatio: titleMeta.aspect, width: "100%" } : undefined}
        >
          <img
            src={url}
            alt="Chart preview"
            className="size-full rounded-md object-contain shadow-sm"
          />
        </div>
      ) : (
        !message && (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <ImageIcon className="size-6 opacity-40" />
            {seen && <span className="text-xs">Rendering…</span>}
          </div>
        )
      )}

      {isFetching && url && (
        <div className="absolute top-2 right-2 size-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      )}

      {message && (
        <div className="absolute inset-2 flex flex-col items-center justify-center gap-1.5 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-center text-destructive">
          <AlertCircleIcon className="size-4 shrink-0" />
          <span className="text-xs leading-snug">{message}</span>
        </div>
      )}
    </div>
  );
}
