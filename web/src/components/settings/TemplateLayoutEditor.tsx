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

type AreaKey = "title" | "content" | "subtitle" | "footer";

/** The two with a box of their own, and the only two drawn on the sample.
 *
 *  The subtitle and the footer are placed RELATIVE to these — a fixed gap above
 *  the chart, a fixed gap above the template's own foot — so there is nothing
 *  about them to drag, and an outline that cannot be moved is furniture sitting
 *  on top of the picture it obscures. They keep their font, size and colour. */
const PLACED: AreaKey[] = ["title", "content"];

const TONE: Record<AreaKey, { border: string; fill: string; chip: string }> = {
  title: { border: "border-sky-500", fill: "bg-sky-500/10", chip: "bg-sky-500" },
  content: { border: "border-emerald-600", fill: "bg-emerald-500/10", chip: "bg-emerald-600" },
  subtitle: { border: "border-violet-400", fill: "bg-violet-400/5", chip: "bg-violet-400" },
  footer: { border: "border-amber-500", fill: "bg-amber-400/5", chip: "bg-amber-500" },
};

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
  const [draft, setDraft] = useState<TemplateLayout["overrides"]>({});
  // What the author is TRYING, which is what the harvested numbers must describe.
  const trying = draft.layout_index ?? null;
  const { data, isLoading } = useQuery({
    queryKey: ["template-layout", customerId, templateId, trying],
    queryFn: () => api.templates.layout(customerId, templateId, trying),
    placeholderData: (previous) => previous,
  });

  // Seeded ONCE per template, not on every refetch. Changing the layout refetches
  // — that is how the boxes move to the new layout's — and re-seeding there would
  // throw away the change that caused it, one keystroke after it was made.
  const seeded = useRef("");
  useEffect(() => {
    const id = `${customerId}/${templateId}`;
    if (data && seeded.current !== id) {
      seeded.current = id;
      setDraft(data.overrides ?? {});
    }
  }, [data, customerId, templateId]);

  const save = useMutation({
    mutationFn: (body: TemplateLayout["overrides"]) =>
      api.templates.saveLayout(customerId, templateId, body),
    onSuccess: (_r, sent) => {
      toast.success("Layout saved");
      setDraft(sent ?? {});
      void qc.invalidateQueries({ queryKey: ["template-layout", customerId, templateId] });
      // Every preview drawn on this template is now stale.
      void qc.removeQueries({ queryKey: ["chart-preview"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Could not save"),
  });

  const layoutIndex = draft.layout_index ?? data?.chosen_layout ?? null;
  // What the author is trying, a beat behind the keystroke. Every change here
  // costs a render on the server, so it waits for them to stop rather than
  // drawing a slide per character.
  const [settled, setSettled] = useState("{}");
  const wanted = JSON.stringify(draft);
  useEffect(() => {
    const t = setTimeout(() => setSettled(wanted), 400);
    return () => clearTimeout(t);
  }, [wanted]);

  const groundUrl = useMemo(
    () => (data
      ? api.templates.sampleUrl(customerId, templateId, layoutIndex, settled)
      : ""),
    [data, customerId, templateId, layoutIndex, settled]
  );
  const areas = data
    ? ({
        title: effective(draft.title, data.harvested.title),
        content: effective(draft.content, data.harvested.content),
        subtitle: effective(draft.subtitle, data.harvested.subtitle),
        footer: effective(draft.footer, data.harvested.footer),
      } as Record<AreaKey, ReturnType<typeof effective>>)
    : null;

  return {
    data, isLoading, draft, setDraft, save, layoutIndex, groundUrl, areas,
    patch: (key: AreaKey, change: Partial<TemplateArea>) =>
      setDraft((d) => ({ ...d, [key]: { ...(d[key] ?? {}), ...change } })),
  };
}

type State = ReturnType<typeof useTemplateLayout>;

/** How far apart the positions an author can choose are, in inches.
 *
 *  A twentieth of an inch. Fine enough that nothing feels stuck, coarse enough
 *  that two areas dragged to "the same" left edge actually share one — which is
 *  the thing that looks wrong on a rendered slide and cannot be seen while
 *  dragging. Typed values are not snapped: somebody entering 1.23 means it.
 */
const SNAP_IN = 0.05;

const snap = (v: number) => Math.round(v / SNAP_IN) * SNAP_IN;
/** Kill the float dust 0.05-steps leave behind (0.30000000000000004). */
const tidy = (v: number) => Math.round(v * 100) / 100;

/** The smallest box worth having. Below this a drag has effectively deleted the
 *  area, and there is no handle left to drag back. */
const MIN_IN = 0.2;

type Edge = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

/** The slide itself, at the proportions the template really has. */
export function TemplateSlidePreview({ state }: { state: State }) {
  const surface = useRef<HTMLDivElement | null>(null);
  const [busy, setBusy] = useState<AreaKey | null>(null);
  const { data, areas, groundUrl, patch } = state;
  if (!data || !areas) return null;
  const slide = data.slide;

  /** One gesture: move the box, or pull one of its edges. */
  const gesture = (key: AreaKey, edge: Edge | null) => (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const box = surface.current?.getBoundingClientRect();
    if (!box) return;
    const perInchX = box.width / slide.w;
    const perInchY = box.height / slide.h;
    const startX = e.clientX;
    const startY = e.clientY;
    const from = { ...areas[key] };
    setBusy(key);

    const move = (ev: PointerEvent) => {
      const dx = (ev.clientX - startX) / perInchX;
      const dy = (ev.clientY - startY) / perInchY;
      if (edge === null) {
        patch(key, {
          x: tidy(Math.max(0, Math.min(slide.w - from.w, snap(from.x + dx)))),
          y: tidy(Math.max(0, Math.min(slide.h - from.h, snap(from.y + dy)))),
        });
        return;
      }
      let { x, y, w, h } = from;
      if (edge.includes("w")) {
        const right = from.x + from.w;
        x = Math.min(snap(from.x + dx), right - MIN_IN);
        w = right - x;
      }
      if (edge.includes("e")) w = Math.max(MIN_IN, snap(from.w + dx));
      if (edge.includes("n")) {
        const bottom = from.y + from.h;
        y = Math.min(snap(from.y + dy), bottom - MIN_IN);
        h = bottom - y;
      }
      if (edge.includes("s")) h = Math.max(MIN_IN, snap(from.h + dy));
      patch(key, {
        x: tidy(Math.max(0, x)), y: tidy(Math.max(0, y)),
        w: tidy(Math.min(w, slide.w - x)), h: tidy(Math.min(h, slide.h - y)),
      });
    };
    const up = () => {
      setBusy(null);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const pct = (v: number, of: number) => `${(v / of) * 100}%`;

  //: Where each handle sits on its box, and which cursor says what it does.
  const HANDLES: Array<[Edge, string, string]> = [
    ["nw", "-top-1 -left-1", "cursor-nwse-resize"],
    ["ne", "-top-1 -right-1", "cursor-nesw-resize"],
    ["sw", "-bottom-1 -left-1", "cursor-nesw-resize"],
    ["se", "-bottom-1 -right-1", "cursor-nwse-resize"],
    ["n", "-top-1 left-1/2 -translate-x-1/2", "cursor-ns-resize"],
    ["s", "-bottom-1 left-1/2 -translate-x-1/2", "cursor-ns-resize"],
    ["w", "top-1/2 -left-1 -translate-y-1/2", "cursor-ew-resize"],
    ["e", "top-1/2 -right-1 -translate-y-1/2", "cursor-ew-resize"],
  ];

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
        className="relative w-full touch-none overflow-hidden rounded-md border bg-white shadow-md ring-1 ring-black/5"
        style={{ aspectRatio: `${slide.w} / ${slide.h}` }}
      >
        <img src={groundUrl} alt="" className="absolute inset-0 h-full w-full object-fill" />
        {/* The grid positions snap to, drawn only while something is moving —
            visible when it explains what is happening, invisible otherwise. */}
        {busy && (
          <div
            className="pointer-events-none absolute inset-0 opacity-70"
            style={{
              backgroundImage:
                "linear-gradient(to right,rgba(59,130,246,.25) 1px,transparent 1px)," +
                "linear-gradient(to bottom,rgba(59,130,246,.25) 1px,transparent 1px)",
              backgroundSize: `${(SNAP_IN / slide.w) * 100}% ${(SNAP_IN / slide.h) * 100}%`,
            }}
          />
        )}
        {PLACED.map((key) => {
          const a = areas[key];
          const tone = TONE[key];
          return (
            <div
              key={key}
              onPointerDown={gesture(key, null)}
              className={`absolute cursor-move border-2 border-dashed ${tone.border} ${tone.fill}`
                + (busy === key ? " shadow-lg" : "")}
              style={{
                left: pct(a.x, slide.w), top: pct(a.y, slide.h),
                width: pct(a.w, slide.w), height: pct(a.h, slide.h),
              }}
              title={`${key} — drag to move, pull an edge to resize`}
            >
              <span
                className={"absolute left-0 top-0 -translate-y-full rounded-t px-1.5 py-0.5 "
                  + `text-[10px] font-medium uppercase tracking-wide text-white ${tone.chip}`}
              >
                {key}
              </span>
              {busy === key && (
                <span className="absolute right-1 top-1 rounded bg-background/90 px-1 py-0.5 text-[10px] font-mono">
                  {a.w.toFixed(2)}″ × {a.h.toFixed(2)}″
                </span>
              )}
              {HANDLES.map(([edge, place, cursor]) => (
                <span
                  key={edge}
                  onPointerDown={gesture(key, edge)}
                  className={`absolute size-2.5 rounded-sm border border-white ${tone.chip} ${place} ${cursor}`}
                />
              ))}
            </div>
          );
        })}
      </div>
      </div>
      <p className="text-center text-xs text-muted-foreground">
        {slide.w}″ × {slide.h}″ — a sample slide as this template draws it. Drag the
        title or content to move it, pull an edge to resize; both snap to {SNAP_IN}″.
        The subtitle and footer follow them.
      </p>
    </div>
  );
}

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
  const { data, areas, patch, draft, setDraft } = state;
  if (!data || !areas) return null;
  const corrected = Object.keys(draft[area] ?? {}).length > 0;
  const values = areas[area];
  const harvested = data.harvested[area];
  const spine = { title: "border-l-sky-500", content: "border-l-emerald-600",
                  subtitle: "border-l-violet-400", footer: "border-l-amber-500" }[area];
  const dot = TONE[area].chip;
  return (
    <fieldset className={`space-y-3 rounded-md border border-l-4 ${spine} bg-muted/30 p-3`}>
      <legend className="flex w-full items-center gap-1.5 px-1 text-sm font-medium capitalize">
        <span className={`size-2 rounded-full ${dot}`} />
        {area}
        {/* Per area, because a correction is usually to ONE of them — putting a
            title back where the template had it should not also throw away a
            chart area that took some dragging to get right. */}
        <button
          type="button"
          onClick={() => setDraft((d) => {
            const next = { ...d };
            delete next[area];
            return next;
          })}
          disabled={!corrected}
          className="ml-auto rounded px-1.5 py-0.5 text-[10px] font-normal normal-case text-muted-foreground hover:bg-muted disabled:opacity-40 disabled:hover:bg-transparent"
          title={corrected ? `Put ${area} back where the template had it`
                           : `${area} is as the template had it`}
        >
          Reset to original
        </button>
      </legend>
      {!PLACED.includes(area) && (
        <p className="text-xs text-muted-foreground">
          {area === "subtitle"
            ? "Sits just above the chart, sharing the title's left edge and width — so it moves when they do."
            : "Sits above the template's own foot, sharing the title's left edge."}
        </p>
      )}
      {PLACED.includes(area) && (
      <div className="grid grid-cols-4 gap-2">
        {(["x", "y", "w", "h"] as const).map((edge) => (
          <div key={edge} className="space-y-1">
            <Label className="text-[10px] uppercase tracking-wide">{edge}″</Label>
            <Input
              type="number" step="0.01" min={0}
              max={edge === "x" || edge === "w" ? data.slide.w : data.slide.h}
              value={values[edge]}
              onChange={(e) => {
                if (e.target.value === "") return patch(area, { [edge]: undefined });
                // Kept on the slide, exactly as a drag is. A typed 99 puts the
                // area somewhere with no handle to drag it back from.
                const limit = edge === "x" || edge === "w" ? data.slide.w : data.slide.h;
                patch(area, {
                  [edge]: Math.max(edge === "w" || edge === "h" ? 0.2 : 0,
                                   Math.min(Number(e.target.value), limit)),
                });
              }}
            />
          </div>
        ))}
      </div>
      )}
      <div className="grid grid-cols-[1.4fr_0.7fr_1.4fr] gap-2">
        <div className="space-y-1">
          <Label className="text-[10px] uppercase tracking-wide">Font</Label>
          <select
            className="h-9 w-full rounded-md border bg-background px-2 text-sm"
            value={values.font ?? ""}
            onChange={(e) => patch(area, { font: e.target.value || undefined })}
          >
            {/* Only fonts this host can draw. A typed name that is not installed
                renders as a stand-in and looks like the setting was ignored. */}
            <option value="">{harvested.font ? `${harvested.font} (as read)` : "inherit"}</option>
            {(data.available_fonts ?? []).map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
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
          <option value="">Whatever we chose ({data.auto_layout ?? "none"})</option>
          {data.layouts.map((l) => (
            <option key={l.index} value={l.index}>
              {l.index === data.auto_layout ? "★ " : ""}
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
      <AreaFields state={state} area="subtitle" />
      <AreaFields state={state} area="content" />
      <AreaFields state={state} area="footer" />

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
