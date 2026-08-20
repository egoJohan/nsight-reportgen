import { useState } from "react";
import { SettingsIcon, AlertTriangleIcon, CheckIcon, ArrowRightIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useTemplateDetail, useSubstitutions } from "@/lib/queries";
import type { TemplateFont } from "@/lib/api";

function bytes(n: number): string {
  return n > 1_000_000 ? `${(n / 1_000_000).toFixed(1)} MB` : `${Math.round(n / 1000)} kB`;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 text-sm">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right">{children}</span>
    </div>
  );
}

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
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="truncate">
              {data?.name ?? "Template settings"}
            </DialogTitle>
            <DialogDescription>
              The template's details and fonts. A substitute affects the
              preview and the PDF only — the PowerPoint file always names the
              template's own font.
            </DialogDescription>
          </DialogHeader>

          {!data ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="space-y-4">
              <div className="rounded-lg border px-3 py-1">
                <Field label="Chart layout">{data.layout_name || "—"}</Field>
                <Field label="Heading font">{data.heading_font || "—"}</Field>
                <Field label="Body font">{data.body_font || "—"}</Field>
                <Field label="Size">{bytes(data.size)}</Field>
                <Field label="Colour palette">
                  <span className="inline-flex gap-0.5 align-middle">
                    {data.palette.map((c) => (
                      <span
                        key={c}
                        title={`#${c}`}
                        className="size-3 rounded-sm border border-border"
                        style={{ backgroundColor: `#${c}` }}
                      />
                    ))}
                  </span>
                </Field>
              </div>

              <div>
                <h4 className="text-sm font-semibold">Fonts</h4>
                <div className="mt-1">
                  {data.fonts.length === 0 && (
                    <p className="py-2 text-xs text-muted-foreground">The template names no fonts.</p>
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
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
