import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { UploadCloudIcon, AlertCircleIcon } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { qk } from "@/lib/queries";
import { setMaterial } from "@/lib/workspace";

/**
 * New case = upload. Picking a SAV creates the case (named from the SAV study
 * label, else the file name), uploads + ingests it, and opens the case with its
 * questions. One step — no empty-case-then-go-to-data.
 */
export default function NewCaseDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    if (!file.name.match(/\.(sav|zsav)$/i)) {
      setError("Please choose a .sav or .zsav SPSS file.");
      return;
    }
    setError(null);
    setBusy(true);
    const base = file.name.replace(/\.(sav|zsav)$/i, "");
    try {
      const { case_id } = await api.cases.create(base);
      const res = await api.materials.upload(case_id, file);
      setMaterial(case_id, res.material_id);
      // Prefer the SAV's embedded study title for the case name.
      const label = (res.file_label ?? "").trim();
      if (label && label !== base) {
        await api.cases.rename(case_id, label).catch(() => {});
      }
      await qc.invalidateQueries({ queryKey: qk.cases() });
      toast.success(`Imported — ${res.question_count} questions curated`);
      onOpenChange(false);
      navigate(`/cases/${case_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!busy) {
          onOpenChange(v);
          if (!v) setError(null);
        }
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New case</DialogTitle>
          <DialogDescription>
            Upload an SPSS file — it becomes a new case, named from the survey's
            title. You can rename it later.
          </DialogDescription>
        </DialogHeader>

        <div
          onDrop={(e) => {
            e.preventDefault();
            const f = e.dataTransfer.files[0];
            if (f && !busy) handleFile(f);
          }}
          onDragOver={(e) => e.preventDefault()}
          className="relative mt-2 flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-border bg-muted/30 px-8 py-12 text-center transition-colors hover:border-primary/50 hover:bg-muted/50"
        >
          <div className="mb-4 flex size-12 items-center justify-center rounded-xl bg-background shadow-sm">
            <UploadCloudIcon className="size-6 text-muted-foreground" />
          </div>
          <p className="text-sm font-medium">
            {busy ? "Importing…" : "Drop your SPSS file here"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            .sav or .zsav — or{" "}
            <button
              type="button"
              className="underline underline-offset-2 hover:text-foreground"
              onClick={() => inputRef.current?.click()}
              disabled={busy}
            >
              browse to choose
            </button>
          </p>
          <input
            ref={inputRef}
            type="file"
            accept=".sav,.zsav"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
              e.target.value = "";
            }}
          />
          {busy && (
            <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-background/80 backdrop-blur-sm">
              <div className="flex flex-col items-center gap-2">
                <div className="size-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                <p className="text-xs text-muted-foreground">
                  Creating case &amp; curating questions…
                </p>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm text-destructive">
            <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
            <span className="leading-snug">{error}</span>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
