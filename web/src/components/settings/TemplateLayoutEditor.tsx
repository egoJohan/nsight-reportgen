/**
 * Where a template's slide actually gets laid out — and where an author
 * corrects it when we read it wrong.
 *
 * We harvest a customer's .pptx: which layout to build on, where the title
 * sits, where the chart goes, what colour the headline is. It is a guess made
 * from a file nobody wrote for us, and on the three customer templates we have
 * it was wrong three different ways — a title colour discarded and drawn black
 * on a black band, a chart put in a half-width column, a 2.61in title box that
 * pushed the question halfway down the slide.
 *
 * So the guess is shown rather than assumed: the template's own empty slide,
 * with the two areas drawn on it as dashed rectangles that can be dragged. The
 * numbers beside them are the same values, for when an author wants an exact
 * one instead of a nudge. Blank means inherit, so a template nobody has touched
 * keeps rendering exactly as harvested.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type TemplateArea, type TemplateLayout } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

type AreaKey = "title" | "content";

/** The value in force: what the author said, else what we harvested. */
function effective(area: TemplateArea | undefined, harvested: Required<TemplateArea>) {
  return {
    x: area?.x ?? harvested.x,
    y: area?.y ?? harvested.y,
    w: area?.w ?? harvested.w,
    h: area?.h ?? harvested.h,
    font: area?.font ?? harvested.font,
    size: area?.size ?? harvested.size,
    colour: area?.colour ?? harvested.colour,
  };
}

export function TemplateLayoutEditor({
  customerId,
  templateId,
}: {
  customerId: string;
  templateId: string;
}) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["template-layout", customerId, templateId],
    queryFn: () => api.templates.layout(customerId, templateId),
  });

  const [draft, setDraft] = useState<TemplateLayout["overrides"]>({});
  const [dragging, setDragging] = useState<AreaKey | null>(null);
  const surface = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (data) setDraft(data.overrides ?? {});
  }, [data]);

  const save = useMutation({
    mutationFn: (body: TemplateLayout["overrides"]) =>
      api.templates.saveLayout(customerId, templateId, body),
    onSuccess: () => {
      toast.success("Layout saved");
      void qc.invalidateQueries({ queryKey: ["template-layout", customerId, templateId] });
      // Every preview drawn on this template is now stale.
      void qc.removeQueries({ queryKey: ["chart-preview"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Could not save"),
  });

  const layoutIndex = draft.layout_index ?? data?.chosen_layout ?? null;
  const groundUrl = useMemo(
    () => (data ? api.templates.groundUrl(customerId, templateId, layoutIndex) : ""),
    [data, customerId, templateId, layoutIndex]
  );

  if (isLoading || !data) {
    return <p className="text-sm text-muted-foreground">Reading the template…</p>;
  }

  const slide = data.slide;
  const areas: Record<AreaKey, ReturnType<typeof effective>> = {
    title: effective(draft.title, data.harvested.title),
    content: effective(draft.content, data.harvested.content),
  };

  const patch = (key: AreaKey, change: Partial<TemplateArea>) =>
    setDraft((d) => ({ ...d, [key]: { ...(d[key] ?? {}), ...change } }));

  /** Drag a box around the slide. Inches throughout — the same unit the fields
   *  show and PowerPoint's own ruler uses. */
  const onPointerDown = (key: AreaKey) => (e: React.PointerEvent) => {
    e.preventDefault();
    const box = surface.current?.getBoundingClientRect();
    if (!box) return;
    const perInchX = box.width / slide.w;
    const perInchY = box.height / slide.h;
    const startX = e.clientX;
    const startY = e.clientY;
    const from = { ...areas[key] };
    setDragging(key);
    const move = (ev: PointerEvent) => {
      patch(key, {
        x: Math.max(0, Math.round((from.x + (ev.clientX - startX) / perInchX) * 100) / 100),
        y: Math.max(0, Math.round((from.y + (ev.clientY - startY) / perInchY) * 100) / 100),
      });
    };
    const up = () => {
      setDragging(null);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const pct = (v: number, of: number) => `${(v / of) * 100}%`;

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <Label htmlFor="layout">Layout</Label>
        <select
          id="layout"
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          value={layoutIndex ?? ""}
          onChange={(e) =>
            setDraft((d) => ({
              ...d,
              layout_index: e.target.value === "" ? undefined : Number(e.target.value),
            }))
          }
        >
          <option value="">Whatever we chose ({data.chosen_layout ?? "none"})</option>
          {data.layouts.map((l) => (
            <option key={l.index} value={l.index}>
              {l.index === data.chosen_layout ? "★ " : ""}
              {l.name}
              {l.suitable ? ` — content ${l.content_pct}% of the slide` : " — no content area"}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">
          Starred is the one we picked. The percentage is how much of the slide that
          layout's own content box covers — below 40% we treat it as a column and
          place the chart ourselves.
        </p>
      </div>

      {/* The template's empty slide, with the two areas on it. */}
      <div
        ref={surface}
        className="relative w-full overflow-hidden rounded-md border bg-muted"
        style={{ aspectRatio: `${slide.w} / ${slide.h}` }}
      >
        <img src={groundUrl} alt="" className="absolute inset-0 h-full w-full object-fill" />
        {(["title", "content"] as AreaKey[]).map((key) => {
          const a = areas[key];
          return (
            <div
              key={key}
              onPointerDown={onPointerDown(key)}
              className={
                "absolute cursor-move border-2 border-dashed " +
                (key === "title"
                  ? "border-sky-500/80 bg-sky-500/10"
                  : "border-emerald-500/80 bg-emerald-500/10") +
                (dragging === key ? " ring-2 ring-offset-1" : "")
              }
              style={{
                left: pct(a.x, slide.w),
                top: pct(a.y, slide.h),
                width: pct(a.w, slide.w),
                height: pct(a.h, slide.h),
              }}
              title={`${key} — drag to move`}
            >
              <span className="absolute -top-5 left-0 rounded bg-background/90 px-1 text-[10px] font-medium">
                {key}
              </span>
            </div>
          );
        })}
      </div>

      {(["title", "content"] as AreaKey[]).map((key) => (
        <fieldset key={key} className="space-y-2 rounded-md border p-3">
          <legend className="px-1 text-sm font-medium capitalize">{key}</legend>
          <div className="grid grid-cols-4 gap-2">
            {(["x", "y", "w", "h"] as const).map((edge) => (
              <div key={edge} className="space-y-1">
                <Label className="text-xs uppercase">{edge} (in)</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={areas[key][edge]}
                  onChange={(e) =>
                    patch(key, { [edge]: e.target.value === "" ? undefined : Number(e.target.value) })
                  }
                />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Font</Label>
              <Input
                value={areas[key].font ?? ""}
                placeholder={data.harvested[key].font || "inherit"}
                onChange={(e) => patch(key, { font: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Size (pt)</Label>
              <Input
                type="number"
                value={areas[key].size || ""}
                placeholder={String(data.harvested[key].size || "inherit")}
                onChange={(e) =>
                  patch(key, { size: e.target.value === "" ? undefined : Number(e.target.value) })
                }
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Colour</Label>
              <Input
                value={areas[key].colour ?? ""}
                placeholder={data.harvested[key].colour || "inherit"}
                onChange={(e) => patch(key, { colour: e.target.value })}
              />
            </div>
          </div>
          {key === "content" && (
            <p className="text-xs text-muted-foreground">
              Font and size here are the chart's own text — the row labels down the
              side, the numbers in the bars, the legend and the axis. Smaller is what
              makes long variable names fit.
            </p>
          )}
        </fieldset>
      ))}

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Accent</Label>
          <Input
            value={draft.accent ?? ""}
            placeholder={data.harvested.accent || "inherit"}
            onChange={(e) => setDraft((d) => ({ ...d, accent: e.target.value }))}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Background</Label>
          <Input
            value={draft.background ?? ""}
            placeholder={data.harvested.background || "inherit"}
            onChange={(e) => setDraft((d) => ({ ...d, background: e.target.value }))}
          />
        </div>
      </div>

      <div className="flex gap-2">
        <Button onClick={() => save.mutate(draft)} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save layout"}
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            setDraft({});
            save.mutate({});
          }}
          disabled={save.isPending}
        >
          Reset to what we read
        </Button>
      </div>
    </div>
  );
}
