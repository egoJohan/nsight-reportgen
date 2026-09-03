import { useState } from "react";
import { SettingsIcon, AlertTriangleIcon, CheckIcon, ArrowRightIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  TemplateLayoutControls, TemplateSlidePreview, useTemplateLayout,
} from "@/components/settings/TemplateLayoutEditor";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useTemplateDetail, useSubstitutions } from "@/lib/queries";
import type { TemplateFont } from "@/lib/api";


/** One font the template names, and what this server will actually draw it as.
 *
 *  A missing font is not an error about the .pptx — that file keeps naming the
 *  real font and looks right wherever it is installed. It is about what WE
 *  rasterise, which is why the fix offered here is a stand-in for rendering
 *  rather than a change to the deck.
 */
function FontRow({
  font,
  available,
  chosen,
  onChoose,
}: {
  font: TemplateFont;
  available: string[];
  chosen: string;
  onChoose: (use: string) => void;
}) {
  const missing = font.state === "unavailable";
  const substituted = font.state === "substituted";

  return (
    <div className="border-t py-3 first:border-t-0">
      <div className="flex items-center gap-2 text-sm">
        {missing ? (
          <AlertTriangleIcon className="size-4 shrink-0 text-amber-600" />
        ) : (
          <CheckIcon className="size-4 shrink-0 text-primary" />
        )}
        <span className="font-medium">{font.family}</span>
        {substituted && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <ArrowRightIcon className="size-3" />
            {font.substitute}
          </span>
        )}
        {font.state === "present" && (
          <span className="text-xs text-muted-foreground">installed</span>
        )}
      </div>

      {(missing || substituted) && (
        <>
          {font.reason && (
            <p className="mt-1 text-xs text-muted-foreground">{font.reason}</p>
          )}
          <div className="mt-2 flex items-center gap-2">
            <label className="text-xs text-muted-foreground">Substitute with</label>
            <select
              className="h-8 min-w-0 flex-1 rounded-lg border border-input bg-surface px-2.5 text-sm"
              value={chosen}
              onChange={(e) => onChoose(e.target.value)}
            >
              <option value="">No substitute</option>
              {available.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
        </>
      )}
    </div>
  );
}

/** The gear beside the bin on a template row: everything about this pohja,
 *  and the one action worth taking from here — choosing stand-ins for fonts
 *  the server cannot supply. */
export default function TemplateSettingsDialog({
  customerId,
  templateId,
}: {
  customerId: string;
  templateId: string;
}) {
  const [open, setOpen] = useState(false);
  const { data } = useTemplateDetail(customerId, open ? templateId : undefined);
  const subs = useSubstitutions();
  const layout = useTemplateLayout(customerId, templateId);

  const map = subs.data?.map ?? {};

  function choose(family: string, use: string) {
    const next = { ...map };
    if (use) next[family] = use;
    else delete next[family];
    subs.save.mutate(next, {
      onSuccess: () =>
        toast.success(
          use
            ? `'${family}' will be drawn as '${use}'`
            : `Substitute removed from '${family}'`
        ),
      onError: (e) => toast.error(e.message),
    });
  }

  return (
    <>
      <Button
        size="icon-sm"
        variant="ghost"
        title="Template settings"
        onClick={() => setOpen(true)}
      >
        <SettingsIcon className="size-4" />
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        {/* Wide, and the slide keeps its own proportions inside it. The picture
            IS the thing being edited — a narrow dialog put it below the fold and
            squeezed a 13x7.5in slide into a thumbnail, which is no way to judge
            where a title sits. */}
        <DialogContent className="flex max-h-[92vh] w-[95vw] flex-col overflow-hidden sm:max-w-[1400px]">
          <DialogHeader>
            <DialogTitle className="truncate">
              {data?.name ?? "Template settings"}
            </DialogTitle>
          </DialogHeader>

          {!data ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="grid min-h-0 flex-1 gap-6 overflow-y-auto lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
              <div className="lg:sticky lg:top-0 lg:self-start lg:pt-2">
                <TemplateSlidePreview state={layout} />
              </div>

              <div className="space-y-6">
                <TemplateLayoutControls state={layout} />

                {/* Fonts stay: this is not about geometry but about whether the
                    machine drawing the preview HAS the face the template names.
                    The old summary rows above are gone — layout, heading font,
                    body font and palette are all shown, and editable, next door. */}
                <div className="rounded-md border bg-muted/30 p-3">
                  <h4 className="text-sm font-medium">
                    Fonts
                    {data.fonts.some((f) => !f.ok) && (
                      <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-200">
                        {data.fonts.filter((f) => !f.ok).length === 1
                          ? "1 needs a stand-in"
                          : `${data.fonts.filter((f) => !f.ok).length} need a stand-in`}
                      </span>
                    )}
                  </h4>
                  <p className="mb-1 mt-2 text-xs text-muted-foreground">
                    A substitute affects the preview and the PDF only — the PowerPoint
                    file always names the template's own font.
                  </p>
                  <div className="mt-1">
                    {data.fonts.length === 0 && (
                      <p className="py-2 text-xs text-muted-foreground">
                        The template names no fonts.
                      </p>
                    )}
                    {data.fonts.map((f) => (
                      <FontRow
                        key={f.family}
                        font={f}
                        available={data.available_fonts}
                        chosen={map[f.family] ?? ""}
                        onChoose={(use) => choose(f.family, use)}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
