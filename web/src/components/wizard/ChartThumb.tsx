import { AlertCircleIcon, ImageIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChartSpec } from "@/lib/api";
import { useChartPreview } from "@/lib/queries";

/**
 * A cached chart preview thumbnail. Backed by the shared useChartPreview cache,
 * so a given chart's preview is formed ONCE and reused across steps/mounts —
 * revisiting Review/Slides no longer re-renders every thumbnail.
 */
export default function ChartThumb({
  materialId,
  chart,
  className,
  renderTitle,
}: {
  materialId: string;
  chart: ChartSpec;
  className?: string;
  // When false, shares the Design preview's cache entry (title-less PNG) so the
  // thumbnail and the large preview render only ONCE per chart.
  renderTitle?: boolean;
}) {
  const { data: url, error, isFetching } = useChartPreview(materialId, chart, {
    renderTitle,
  });
  const message =
    error instanceof Error ? error.message : error ? "Preview failed" : null;

  return (
    <div
      className={cn(
        "relative flex w-full items-center justify-center overflow-hidden rounded-lg border bg-muted/30 p-3",
        className
      )}
    >
      {url ? (
        <img
          src={url}
          alt="Chart preview"
          className="max-h-full max-w-full rounded-md object-contain shadow-sm"
        />
      ) : (
        !message && (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <ImageIcon className="size-6 opacity-40" />
            <span className="text-xs">Rendering…</span>
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
