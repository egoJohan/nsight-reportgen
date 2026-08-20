import { useEffect, useRef, useState } from "react";
import type { ChartPreviewTitleMeta } from "@/lib/api";

// PowerPoint's own long-standing default slide HEIGHT, in inches — both the
// classic 4:3 (10 x 7.5) and the modern 16:9 widescreen (13.333 x 7.5) format
// share it, and it's the same fallback this codebase's own renderer falls
// back to when a template states nothing (fast_preview.py's ground_image,
// `Inches(7.5)`). The backend sends the slide's ASPECT rather than its
// absolute size (X-Slide-Aspect), so this constant is what turns a point size
// into a pixel one without a second header round trip.
const ASSUMED_SLIDE_HEIGHT_IN = 7.5;

/**
 * The template's title, drawn in DOM over the fast-composited preview image.
 *
 * The fast path (render_title=false) never bakes a title into the PNG — see
 * routes_questions.py — because the frontend owns that region instead. This
 * is the one place that draws it, so SlideGrid's thumbnails and ChartThumb's
 * don't each re-derive the box.
 *
 * Renders nothing when there is no title text or no box: the same "no title"
 * outcome a preview with none has today. Positioned as a percentage of ITS
 * OWN container, which the caller must size to the same box the <img> fills
 * (e.g. by giving that container `aspectRatio: meta.aspect` instead of a
 * fixed CSS ratio) — that is what keeps the text and the image from drifting
 * apart on resize, rather than two components separately computing a box.
 */
export default function SlideTitleOverlay({
  title,
  meta,
}: {
  title: string | null | undefined;
  meta: ChartPreviewTitleMeta | null | undefined;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // Tracked so type scales with however big the thumbnail/pane is actually
  // rendered, at both grid-thumbnail and full-pane size, and follows a resize
  // (a window resize, a sidebar toggle) without a remount.
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const text = (title ?? "").trim();
  if (!text || !meta) return null;

  const [left, top, boxWidth, boxHeight] = meta.box;
  // The container's height in px, given the aspect ratio it was told to take
  // on (meta.aspect) — see the caller. Falls back to 0 until the first
  // ResizeObserver callback, at which point the box below renders.
  const heightPx = width / meta.aspect;
  const fontSizePx = (meta.sizePt / 72) * (heightPx / ASSUMED_SLIDE_HEIGHT_IN);

  return (
    <div ref={ref} className="pointer-events-none absolute inset-0 z-10 overflow-hidden">
      {width > 0 && (
        <div
          className={meta.caps ? "uppercase" : undefined}
          style={{
            position: "absolute",
            left: `${left * 100}%`,
            top: `${top * 100}%`,
            width: `${boxWidth * 100}%`,
            height: `${boxHeight * 100}%`,
            fontSize: `${fontSizePx}px`,
            lineHeight: 1.15,
            color: `#${meta.color}`,
            fontFamily: meta.font ? `"${meta.font}", sans-serif` : undefined,
            textAlign: meta.align,
          }}
        >
          {text}
        </div>
      )}
    </div>
  );
}
