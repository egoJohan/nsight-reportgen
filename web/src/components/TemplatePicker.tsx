import { useRef, useState } from "react";
import {
  UploadIcon, Trash2Icon, CheckIcon, Loader2Icon, AlertTriangleIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { PANEL } from "@/lib/surfaces";
import { useTemplates, useTemplateActions } from "@/lib/queries";
import TemplateSettingsDialog from "@/components/TemplateSettingsDialog";
import type { Template, TemplateFont } from "@/lib/api";

/** Fonts this template names that the render host cannot supply.
 *
 *  A deck still renders without them — LibreOffice substitutes — so this is a
 *  warning on the row rather than a block on using the template. What it buys
 *  is that nobody sends a deck in the wrong typeface without having been told.
 */
function missingFonts(t: Template): TemplateFont[] {
  return (t.fonts ?? []).filter((f) => !f.ok);
}

/** Where a binding is being made. The wording differs per level because
 *  "inherited" means something different at each one. */
export type TemplateLevel = "customer" | "case" | "report";

const LEVEL_LABEL: Record<TemplateLevel, string> = {
  customer: "asiakkaalle",
  case: "tutkimukselle",
  report: "raportille",
};

/** Templates are stored per CUSTOMER even when bound to a tutkimus or a report:
 *  the same client deck is reused across their studies, and uploading it once
 *  per report would be absurd. So every level picks from the customer's list. */
export default function TemplatePicker({
  customerId,
  level,
  currentId,
  inheritedFrom,
  onBind,
}: {
  customerId: string;
  level: TemplateLevel;
  /** The template bound AT THIS LEVEL, or "" when inheriting. */
  currentId: string;
  /** Human text for what applies when nothing is bound here. */
  inheritedFrom?: string;
  onBind: (templateId: string | null) => void;
}) {
  const { data: templates, isLoading } = useTemplates(customerId);
  const actions = useTemplateActions(customerId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setBusy(true);
    try {
      const created = await actions.upload.mutateAsync(file);
      // Uploading here means "use this one" — otherwise the file lands in a
      // list and nothing visibly happens, which reads as a failure.
      onBind(created.id);
      if (created.warnings?.length) {
        // Every warning, not just the first: a deck naming two unavailable
        // fonts has two separate things for someone to act on.
        created.warnings.forEach((w) => toast.warning(w, { duration: 12000 }));
      } else {
        toast.success(`${created.name} otettu käyttöön`);
      }
    } catch (e) {
      // The server rejects a template it cannot render into, with the reason.
      toast.error(e instanceof Error ? e.message : "Pohjan lataus epäonnistui");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className={`${PANEL} p-4`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">Esityspohja</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {currentId
              ? `Asetettu ${LEVEL_LABEL[level]}.`
              : inheritedFrom
                ? `Peritty: ${inheritedFrom}`
                : "Käytössä nSightin oletuspohja."}
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => fileRef.current?.click()}
        >
          {busy ? (
            <Loader2Icon className="mr-2 size-4 animate-spin" />
          ) : (
            <UploadIcon className="mr-2 size-4" />
          )}
          Lataa pohja
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept=".pptx"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
          }}
        />
      </div>

      <div className="mt-3 space-y-1">
        {isLoading && <p className="text-xs text-muted-foreground">Ladataan…</p>}

        {templates?.length === 0 && !isLoading && (
          <p className="text-xs text-muted-foreground">
            Ei vielä pohjia. Lataa asiakkaan oma PowerPoint-pohja.
          </p>
        )}

        {templates?.map((t: Template) => {
          const active = t.id === currentId;
          return (
            <div
              key={t.id}
              className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 hover:bg-accent"
            >
              <button
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
                onClick={() => onBind(active ? null : t.id)}
                title={active ? "Poista valinta (peri ylemmältä)" : "Ota käyttöön"}
              >
                <CheckIcon
                  className={`size-4 shrink-0 ${active ? "text-primary" : "opacity-0"}`}
                />
                <span className="min-w-0">
                  <span className="block truncate text-sm">{t.name}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {t.layout_name}
                    {t.heading_font ? ` · ${t.heading_font}` : ""}
                  </span>
                  {missingFonts(t).length > 0 && (
                    <span
                      className="mt-0.5 flex items-center gap-1 text-xs text-destructive"
                      title={missingFonts(t)
                        .map((f) => f.reason)
                        .join("\n\n")}
                    >
                      <AlertTriangleIcon className="size-3 shrink-0" />
                      <span className="truncate">
                        Fontti puuttuu:{" "}
                        {missingFonts(t)
                          .map((f) => f.family)
                          .join(", ")}
                      </span>
                    </span>
                  )}
                </span>
                {/* The palette is the fastest way to recognise a client's deck. */}
                <span className="ml-auto flex shrink-0 gap-0.5">
                  {t.palette.slice(0, 4).map((c) => (
                    <span
                      key={c}
                      className="size-3 rounded-sm border border-border"
                      style={{ backgroundColor: `#${c}` }}
                    />
                  ))}
                </span>
              </button>
              {/* Settings before delete: the gear is the one you want most of
                  the time, and putting it left of the bin keeps a destructive
                  button from being the default target. */}
              <TemplateSettingsDialog customerId={customerId} templateId={t.id} />
              <Button
                size="icon-sm"
                variant="ghost"
                className="text-muted-foreground hover:text-destructive"
                title="Poista pohja"
                onClick={() => actions.remove.mutate(t.id)}
              >
                <Trash2Icon className="size-4" />
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
