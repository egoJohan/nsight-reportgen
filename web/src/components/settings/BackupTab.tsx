import { useRef, useState } from "react";
import {
  DownloadIcon,
  UploadIcon,
  Loader2Icon,
  AlertTriangleIcon,
  DatabaseIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { RestoreResult } from "@/lib/api";
import { PANEL } from "@/lib/surfaces";

/** Settings > Backup — admin only (see SettingsPage).
 *
 *  Two halves of one job: take a copy of everything, and put it back. The
 *  backup holds settings, users and grants, customers, studies, the uploaded
 *  SAVs, report definitions, brand templates and fonts. Rendered decks are
 *  left out — they are regenerated from the report definitions and templates
 *  that ARE in there, and they are the one thing large enough to make a
 *  backup impractical.
 */
export default function BackupTab() {
  const [creating, setCreating] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<RestoreResult | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function createBackup() {
    setCreating(true);
    try {
      const { blob, filename } = await api.backup.download();
      // Save it by clicking a link at an object URL: the request has already
      // been made and authenticated, so this only names the file the browser
      // writes. Revoked straight after, or the blob stays in memory.
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Backup downloaded");
    } catch (e) {
      toast.error(`Backup failed: ${(e as Error).message}`);
    } finally {
      setCreating(false);
    }
  }

  async function restore() {
    if (!file) return;
    setRestoring(true);
    try {
      const summary = await api.backup.restore(file);
      setResult(summary);
      setConfirming(false);
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      toast.success(`Restored ${summary.restored} objects`);
    } catch (e) {
      toast.error(`Restore failed: ${(e as Error).message}`);
    } finally {
      setRestoring(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className={PANEL}>
        <h2 className="text-sm font-semibold">Create backup</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Downloads everything nSight keeps as one zip: settings, users and
          their permissions, customers, studies, the SPSS files that were
          uploaded, report definitions, templates and fonts. Generated decks
          are not included — they are rebuilt from the reports and templates
          that are, so restored reports come back as drafts.
        </p>
        <div className="mt-3 flex items-start gap-2 text-sm text-amber-700 dark:text-amber-500">
          <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
          {/* Said plainly at the point of download, not buried in a doc: the
              file is as sensitive as the database it came from. */}
          <p className="max-w-2xl">
            The file contains password hashes and the session signing key.
            Keep it somewhere you would keep a password database.
          </p>
        </div>
        <Button className="mt-4" onClick={createBackup} disabled={creating}>
          {creating ? (
            <Loader2Icon className="size-4 animate-spin" />
          ) : (
            <DownloadIcon className="size-4" />
          )}
          Create backup
        </Button>
      </section>

      <section className={PANEL}>
        <h2 className="text-sm font-semibold">Restore backup</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Writes a backup's contents back into the store. Anything at the same
          place is overwritten; anything not in the backup is left alone — so
          this restores what was lost without deleting what survived. A
          customer deleted after the backup was taken will come back.
        </p>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Everyone, including you, is signed out afterwards: the restore
          replaces the users and the key their sessions are signed with.
        </p>
        <div className="mt-4 flex items-center gap-2">
          <Input
            ref={fileInput}
            type="file"
            accept=".zip,application/zip"
            className="max-w-sm"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setResult(null);
            }}
          />
          <Button variant="outline" disabled={!file} onClick={() => setConfirming(true)}>
            <UploadIcon className="size-4" />Restore
          </Button>
        </div>

        {/* Confirmed by typing the word, not by clicking "OK": a restore
            cannot be undone, and a dialog dismissed with one click is not a
            decision anyone made. */}
        <ConfirmRestore
          file={file}
          open={confirming}
          busy={restoring}
          onCancel={() => setConfirming(false)}
          onConfirm={restore}
        />

        {result && (
          <div className="mt-4 rounded-md border border-border p-3 text-sm">
            <p className="flex items-center gap-2 font-medium">
              <DatabaseIcon className="size-4" />
              Restored {result.restored} objects
              {result.total_bytes > 0 &&
                ` (${Math.round(result.total_bytes / 1024 / 1024)} MB)`}
            </p>
            {result.problems.length > 0 && (
              <>
                <p className="mt-2 text-amber-700 dark:text-amber-500">
                  {result.problems.length} could not be restored:
                </p>
                <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                  {result.problems.slice(0, 10).map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
                {result.problems.length > 10 && (
                  <p className="mt-1 text-muted-foreground">
                    …and {result.problems.length - 10} more.
                  </p>
                )}
              </>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function ConfirmRestore({
  file,
  open,
  busy,
  onCancel,
  onConfirm,
}: {
  file: File | null;
  open: boolean;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const expected = "RESTORE";

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setTyped("");
          onCancel();
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Restore from this backup?</DialogTitle>
          <DialogDescription>
            {file?.name} will be written over the current data. Objects in the
            backup replace what is at the same place; anything not in it stays.
            This cannot be undone, and everyone will be signed out.
          </DialogDescription>
        </DialogHeader>
        <div>
          <p className="mb-2 text-sm text-muted-foreground">
            Type <span className="font-mono font-semibold">{expected}</span> to
            confirm.
          </p>
          <Input
            autoFocus
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={expected}
          />
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              setTyped("");
              onCancel();
            }}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={typed !== expected || busy}
            onClick={() => {
              setTyped("");
              onConfirm();
            }}
          >
            {busy && <Loader2Icon className="size-4 animate-spin" />}
            Restore
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
