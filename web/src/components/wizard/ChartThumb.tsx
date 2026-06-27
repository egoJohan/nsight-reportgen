import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircleIcon, ImageIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { ChartSpec } from "@/lib/api";

/**
 * A live, debounced chart preview thumbnail. Shares the same
 * previewChart → object-URL → revoke lifecycle as StepConfigure's large
 * preview, but at a caller-controlled height and with inline 422 handling.
 */
export default function ChartThumb({
  materialId,
  chart,
  className,
}: {
  materialId: string;
  chart: ChartSpec;
  className?: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const urlRef = useRef<string | null>(null);

  // Only the fields that change the rendered PNG (ignore slot/slide_*).
  const key = useMemo(
    () =>
      JSON.stringify({
        question_ref: chart.question_ref,
        chart_type: chart.chart_type,
        statistic: chart.statistic,
        classifying_var: chart.classifying_var,
        number_format: chart.number_format,
        sort: chart.sort,
        elements: chart.elements,
        scatter_xy: chart.scatter_xy,
        show_not_answered: chart.show_not_answered,
      }),
    [chart]
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const handle = setTimeout(async () => {
      try {
        const blob = await api.materials.previewChart(materialId, chart);
        if (cancelled) return;
        const next = URL.createObjectURL(blob);
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = next;
        setUrl(next);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Preview failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, materialId]);

  useEffect(
    () => () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    },
    []
  );

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
        !error && (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <ImageIcon className="size-6 opacity-40" />
            <span className="text-xs">Rendering…</span>
          </div>
        )
      )}

      {loading && url && (
        <div className="absolute top-2 right-2 size-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      )}

      {error && (
        <div className="absolute inset-2 flex flex-col items-center justify-center gap-1.5 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-center text-destructive">
          <AlertCircleIcon className="size-4 shrink-0" />
          <span className="text-xs leading-snug">{error}</span>
        </div>
      )}
    </div>
  );
}
