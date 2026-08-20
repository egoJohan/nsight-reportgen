import { useRef, useState } from "react";
import {
  UploadIcon, Trash2Icon, CheckIcon, Loader2Icon, AlertTriangleIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { PANEL, PANEL_TITLE } from "@/lib/surfaces";
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

/** Templates are stored per CUSTOMER even when bound to a tutkimus or a report:
 *  the same client deck is reused across their studies, and uploading it once
 *  per report would be absurd. So every level picks from the customer's list. */
export default function TemplatePicker({
  customerId,
  currentId,
  inheritedFrom,
  onBind,
  manageLibrary = false,
}: {
  customerId: string;
  /** The template bound AT THIS LEVEL, or "" when inheriting. */
  currentId: string;
  /** WHERE the pohja comes from when nothing is bound here — the asiakas's
   *  name, not the template's file name, because that is what tells you where
   *  to go and change it. There is no `level` prop: the panel is identical
   *  wherever it appears, and this is the only thing that differs. */
  inheritedFrom?: string;
  onBind: (templateId: string | null) => void;
  /** May this panel change the ASIAKAS's library — upload, configure, delete?
   *
   *  True only on the asiakas's own page. The templates belong to the asiakas
   *  and are shared by every tutkimus under it, so deleting one from a single
   *  study would take it away from the others, and its font settings are the
   *  asiakas's too. From a tutkimus you choose which of them applies; you do
   *  not edit the library you are choosing from. */
  manageLibrary?: boolean;
}) {
  const { data: templates, isLoading } = useTemplates(customerId);
  const actions = useTemplateActions(customerId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Template | null>(null);

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
    <div className={`${PANEL} px-3 py-2.5`}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 className={PANEL_TITLE}>Esityspohja</h3>
          {/* Only says something when the pohja is NOT set here: where it IS
              set, the panel's own position already says so. */}
          <p className="text-xs text-muted-foreground">
            {currentId
              ? "Valittu tälle. Poista valinta palataksesi perittyyn pohjaan."
              : inheritedFrom
                ? `Peritty asiakkaalta ${inheritedFrom}. Valitse alta, jos haluat käyttää tässä toista pohjaa.`
                : "Käytössä nSightin oletuspohja. Valitse alta ottaaksesi pohjan käyttöön."}
          </p>
        </div>
        {manageLibrary && (
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
        )}
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

      <div className="mt-2 space-y-0.5">
        {isLoading && <p className="text-xs text-muted-foreground">Ladataan…</p>}

        {templates?.length === 0 && !isLoading && (
          <p className="text-xs text-muted-foreground">
            {manageLibrary
              ? "Ei vielä pohjia. Lataa asiakkaan oma PowerPoint-pohja."
              : "Asiakkaalle ei ole lisätty pohjia. Lisää ne asiakkaan sivulla."}
          </p>
        )}

        {templates?.map((t: Template) => {
          const active = t.id === currentId;
          return (
            <div
              key={t.id}
              className="flex items-center justify-between gap-2 rounded-md px-2 py-1 hover:bg-accent"
            >
              <button
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
                onClick={() => onBind(active ? null : t.id)}
                title={active ? "Poista valinta (peri ylemmältä)" : "Ota käyttöön"}
              >
                {/* Always visible, selected or not. An invisible checkmark
                    left an unselected list looking like a read-only display —
                    on the tutkimus page, where the upload/settings/delete
                    buttons are absent, there was then nothing at all to say the
                    rows could be clicked. */}
                <span
                  className={`flex size-4 shrink-0 items-center justify-center rounded-full border ${
                    active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-muted-foreground/40"
                  }`}
                >
                  {active && <CheckIcon className="size-3" />}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm">{t.name}</span>
                  {missingFonts(t).length > 0 && (
                    <span
                      className="flex items-center gap-1 text-xs text-destructive"
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
                  button from being the default target. Both belong to the
                  asiakas — a font stand-in is set once for the template, not
                  per tutkimus — so neither appears when choosing. */}
              {manageLibrary && (
                <TemplateSettingsDialog customerId={customerId} templateId={t.id} />
              )}
              {/* This deletes the FILE from the asiakas, not "stop using it
                  here" — that is the checkmark above, which unbinds and falls
                  back to what is inherited. The two are one click apart and
                  read alike, so the destructive one asks first and names what
                  it takes with it. */}
              {manageLibrary && (
                <Button
                  size="icon-sm"
                  variant="ghost"
                  className="text-muted-foreground hover:text-destructive"
                  title="Poista pohja asiakkaalta"
                  onClick={() => setConfirmDelete(t)}
                >
                  <Trash2Icon className="size-4" />
                </Button>
              )}
            </div>
          );
        })}
      </div>

      <Dialog
        open={confirmDelete !== null}
        onOpenChange={(v) => !v && setConfirmDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Poistetaanko pohja?</DialogTitle>
            <DialogDescription>
              “{confirmDelete?.name}” poistetaan asiakkaalta kokonaan, myös
              niistä tutkimuksista ja raporteista, jotka käyttävät sitä. Ne
              siirtyvät käyttämään ylemmän tason pohjaa. Toimintoa ei voi perua.
              <br />
              <br />
              Jos haluat vain lopettaa tämän pohjan käytön täällä, poista
              valinta listasta.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(null)}>
              Peruuta
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (confirmDelete) actions.remove.mutate(confirmDelete.id);
                setConfirmDelete(null);
              }}
            >
              Poista pohja
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
