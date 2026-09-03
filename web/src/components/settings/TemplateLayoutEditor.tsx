/**
 * Where a template's slide gets laid out — and where an author corrects it.
 *
 * We harvest a customer's .pptx: which layout to build on, where the title
 * sits, where the chart goes, what colour the headline is. It is a guess made
 * from a file nobody wrote for us, and on the three customer templates we have
 * it was wrong three different ways — a title colour discarded and drawn black
 * on a black band, a chart put in a half-width column, a 2.61in title box that
 * pushed the question halfway down the slide.
 *
 * So the guess is SHOWN. The template's own empty slide, at the proportions it
 * really has, with the two areas drawn on it as dashed rectangles that can be
 * dragged. The numbers beside them are the same values for when an author wants
 * an exact one. Blank means inherit, so a template nobody has touched keeps
 * rendering exactly as harvested.
 *
 * Split into a preview and its controls because they belong side by side: the
 * picture is the point, and a column of fields next to it is what makes the
 * picture answerable. One hook holds the state both halves read.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type TemplateArea, type TemplateLayout } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

type AreaKey = "title" | "content";

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

export function useTemplateLayout(customerId: string, templateId: string) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["template-layout", customerId, templateId],
    queryFn: () => api.templates.layout(customerId, templateId),
  });
  const [draft, setDraft] = useState<TemplateLayout["overrides"]>({});
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
  const areas = data
    ? {
        title: effective(draft.title, data.harvested.title),
        content: effective(draft.content, data.harvested.content),
      }
    : null;

  return {
    data, isLoading, draft, setDraft, save, layoutIndex, groundUrl, areas,
    patch: (key: AreaKey, change: Partial<TemplateArea>) =>
      setDraft((d) => ({ ...d, [key]: { ...(d[key] ?? {}), ...change } })),
  };
}

type State = ReturnType<typeof useTemplateLayout>;

/** The slide itself, at the proportions the template really has. */
export function TemplateSlidePreview({ state }: { state: State }) {
  const surface = useRef<HTMLDivElement | null>(null);
  const [dragging, setDragging] = useState<AreaKey | null>(null);
  const { data, areas, groundUrl, patch } = state;
  if (!data || !areas) return null;
  const slide = data.slide;

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
    const move = (ev: PointerEvent) =>
      patch(key, {
        x: Math.max(0, Math.round((from.x + (ev.clientX - startX) / perInchX) * 100) / 100),
        y: Math.max(0, Math.round((from.y + (ev.clientY - startY) / perInchY) * 100) / 100),
      });
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
    <div className="space-y-2">
      {/* A checkered mat, so a white slide on a white dialog still reads as a
          slide with edges. */}
      <div
        className="rounded-lg p-4"
        style={{
          backgroundImage:
            "linear-gradient(45deg,rgba(0,0,0,.04) 25%,transparent 25%,transparent 75%,rgba(0,0,0,.04) 75%)," +
            "linear-gradient(45deg,rgba(0,0,0,.04) 25%,transparent 25%,transparent 75%,rgba(0,0,0,.04) 75%)",
          backgroundSize: "16px 16px",
          backgroundPosition: "0 0, 8px 8px",
        }}
      >
      <div
        ref={surface}
        className="relative w-full overflow-hidden rounded-md border bg-white shadow-md ring-1 ring-black/5"
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
                "absolute cursor-move border-2 border-dashed transition-shadow " +
                (key === "title"
                  ? "border-sky-500 bg-sky-500/10"
                  : "border-emerald-600 bg-emerald-500/10") +
                (dragging === key ? " shadow-lg" : "")
              }
              style={{
                left: pct(a.x, slide.w), top: pct(a.y, slide.h),
                width: pct(a.w, slide.w), height: pct(a.h, slide.h),
              }}
              title={`${key} — drag to move`}
            >
              <span
                className={
                  "absolute left-0 top-0 -translate-y-full rounded-t px-1.5 py-0.5 text-[10px] " +
                  "font-medium uppercase tracking-wide text-white " +
                  (key === "title" ? "bg-sky-500" : "bg-emerald-600")
                }
              >
                {key}
              </span>
            </div>
          );
        })}
      </div>
      </div>
      <p className="text-center text-xs text-muted-foreground">
        {slide.w}″ × {slide.h}″ — the template's own empty slide.
        Drag either area to move it; the numbers follow.
      </p>
    </div>
  );
}

/** A colour, as a swatch to click and a hex to type. Empty is "inherit", which
 *  is why the swatch shows the harvested value while the text stays blank. */
function ColourField({
  label, value, inherited, onChange,
}: {
  label: string; value: string; inherited: string; onChange: (v: string) => void;
}) {
  const shown = (value || inherited || "").replace(/^#/, "");
  return (
    <div className="space-y-1">
      <Label className="text-[10px] uppercase tracking-wide">{label}</Label>
      <div className="flex items-center gap-1.5">
        <input
          type="color"
          aria-label={`${label} colour`}
          value={`#${shown || "000000"}`}
          onChange={(e) => onChange(e.target.value.replace(/^#/, "").toUpperCase())}
          className="size-8 shrink-0 cursor-pointer rounded-md border bg-background p-0.5"
        />
        <Input
          value={value ?? ""}
          placeholder={inherited || "inherit"}
          onChange={(e) => onChange(e.target.value)}
          className="font-mono text-xs"
        />
      </div>
    </div>
  );
}

function AreaFields({ state, area }: { state: State; area: AreaKey }) {
  const { data, areas, patch } = state;
  if (!data || !areas) return null;
  const values = areas[area];
  const harvested = data.harvested[area];
  const spine = area === "title" ? "border-l-sky-500" : "border-l-emerald-600";
  const dot = area === "title" ? "bg-sky-500" : "bg-emerald-600";
  return (
    <fieldset className={`space-y-3 rounded-md border border-l-4 ${spine} bg-muted/30 p-3`}>
      <legend className="flex items-center gap-1.5 px-1 text-sm font-medium capitalize">
        <span className={`size-2 rounded-full ${dot}`} />
        {area}
      </legend>
      <div className="grid grid-cols-4 gap-2">
        {(["x", "y", "w", "h"] as const).map((edge) => (
          <div key={edge} className="space-y-1">
            <Label className="text-[10px] uppercase tracking-wide">{edge}″</Label>
            <Input
              type="number" step="0.01" value={values[edge]}
              onChange={(e) =>
                patch(area, { [edge]: e.target.value === "" ? undefined : Number(e.target.value) })
              }
            />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-[1.4fr_0.7fr_1.4fr] gap-2">
        <div className="space-y-1">
          <Label className="text-[10px] uppercase tracking-wide">Font</Label>
          <Input
            value={values.font ?? ""} placeholder={harvested.font || "inherit"}
            onChange={(e) => patch(area, { font: e.target.value })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-[10px] uppercase tracking-wide">Size</Label>
          <Input
            type="number" value={values.size || ""}
            placeholder={String(harvested.size || "—")}
            onChange={(e) =>
              patch(area, { size: e.target.value === "" ? undefined : Number(e.target.value) })
            }
          />
        </div>
        <ColourField
          label="Colour" value={values.colour ?? ""} inherited={harvested.colour}
          onChange={(v) => patch(area, { colour: v })}
        />
      </div>
      {area === "content" && (
        <p className="text-xs text-muted-foreground">
          Font and size here are the chart's own text — the row labels, the numbers in
          the bars, the legend, the axis. Smaller is what makes long variable names fit.
        </p>
      )}
    </fieldset>
  );
}

/** Everything that can be changed, beside the picture of what it changes. */
export function TemplateLayoutControls({ state }: { state: State }) {
  const { data, draft, setDraft, save, layoutIndex } = state;
  if (!data) return null;
  const anyOverride = Object.keys(draft).length > 0;
  const dirty = JSON.stringify(draft) !== JSON.stringify(data.overrides ?? {});
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
          layout's own content box covers — below 40% we treat it as a column and place
          the chart ourselves.
        </p>
      </div>

      <AreaFields state={state} area="title" />
      <AreaFields state={state} area="content" />

      <fieldset className="grid grid-cols-2 gap-2 rounded-md border bg-muted/30 p-3">
        <legend className="px-1 text-sm font-medium">Colours</legend>
        <ColourField
          label="Accent" value={draft.accent ?? ""} inherited={data.harvested.accent}
          onChange={(v) => setDraft((d) => ({ ...d, accent: v }))}
        />
        <ColourField
          label="Background" value={draft.background ?? ""}
          inherited={data.harvested.background}
          onChange={(v) => setDraft((d) => ({ ...d, background: v }))}
        />
      </fieldset>

      {/* Stuck to the bottom of the column: the fonts section below is long, and
          an author who has just dragged something should not have to hunt for
          the button that keeps it. */}
      <div className="sticky bottom-0 -mx-1 flex items-center gap-2 border-t bg-background/95 px-1 py-3 backdrop-blur">
        <Button onClick={() => save.mutate(draft)} disabled={save.isPending || !dirty}>
          {save.isPending ? "Saving…" : "Save layout"}
        </Button>
        <Button
          variant="outline"
          onClick={() => { setDraft({}); save.mutate({}); }}
          disabled={save.isPending || !anyOverride}
        >
          Reset to what we read
        </Button>
        <span className="ml-auto text-xs text-muted-foreground">
          {dirty ? "Unsaved changes" : anyOverride ? "Corrected" : "As harvested"}
        </span>
      </div>
    </div>
  );
}
