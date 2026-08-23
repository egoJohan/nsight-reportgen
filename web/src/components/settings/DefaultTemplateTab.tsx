import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUpIcon, Loader2Icon, RotateCcwIcon } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { PANEL, PANEL_TITLE } from "@/lib/surfaces";

/** The template every report falls back to.
 *
 *  A report renders on the first template it finds going up: its own, its
 *  tutkimus's, its asiakas's — and this when none of those binds one. nSight
 *  ships one and seeds it at boot, which is what a fresh instance uses; this
 *  replaces that, for everyone.
 *
 *  Its own tab rather than a panel inside Fonts: fonts are about what the
 *  render host can supply, this is about what the whole tenant's work looks
 *  like, and burying it under a typeface list would hide the more consequential
 *  of the two.
 */
export default function DefaultTemplateTab() {
  const qc = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "default-template"],
    queryFn: api.settings.defaultTemplate,
  });

  const done = (next: { warnings?: string[] }) => {
    qc.invalidateQueries({ queryKey: ["settings", "default-template"] });
    // Every preview and every deck is keyed on the template's CONTENT, so a new
    // default re-renders on its own. Nothing to clear by hand.
    qc.invalidateQueries({ queryKey: ["chart-preview"] });
    for (const w of next.warnings ?? []) toast.warning(w);
  };

  const upload = useMutation({
    mutationFn: (file: File) => api.settings.uploadDefaultTemplate(file),
    onSuccess: (next) => {
      done(next);
      toast.success(`"${next.name}" is now the default template`);
    },
    onError: (e: Error) => toast.error(e.message),
    onSettled: () => setBusy(false),
  });

  const restore = useMutation({
    mutationFn: () => api.settings.restoreDefaultTemplate(),
    onSuccess: (next) => {
      done(next);
      toast.success("nSight's own template is the default again");
    },
    onError: (e: Error) => toast.error(e.message),
    onSettled: () => setBusy(false),
  });

  return (
    <div className={PANEL}>
      <h2 className={PANEL_TITLE}>Default template</h2>
      <p className="text-sm text-muted-foreground">
        What a report comes out on when neither it, its study, nor its customer
        has a template of its own. Uploading one here changes how every such
        report looks — including reports that already exist.
      </p>

      <div className="mt-4 rounded-lg border bg-muted/30 p-4">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <>
            <p className="text-sm">
              <span className="text-muted-foreground">In use: </span>
              <span className="font-medium">{data?.name}</span>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {data?.is_builtin
                ? "The template nSight ships. Nothing has been uploaded here."
                : `Uploaded ${data?.uploaded_at?.slice(0, 10) || "—"}`}
              {data?.size ? ` · ${Math.round(data.size / 1024)} kB` : ""}
            </p>
          </>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input
          ref={fileInput}
          type="file"
          accept=".pptx"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            // Reset first: choosing the SAME file twice fires no change event
            // otherwise, so a corrected re-upload would look like a dead button.
            e.target.value = "";
            if (!file) return;
            setBusy(true);
            upload.mutate(file);
          }}
        />
        <Button disabled={busy} onClick={() => fileInput.current?.click()}>
          {upload.isPending ? (
            <Loader2Icon className="size-4 animate-spin" />
          ) : (
            <FileUpIcon className="size-4" />
          )}
          Upload a template
        </Button>
        {!data?.is_builtin && (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              restore.mutate();
            }}
          >
            {restore.isPending ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : (
              <RotateCcwIcon className="size-4" />
            )}
            Restore nSight's template
          </Button>
        )}
      </div>

      <p className="mt-3 text-xs text-muted-foreground">
        A .pptx, checked the same way a customer's template is: it needs a layout
        with a title and a large content area for the chart. If it cannot work,
        it is refused and the current default is left alone.
      </p>
    </div>
  );
}
