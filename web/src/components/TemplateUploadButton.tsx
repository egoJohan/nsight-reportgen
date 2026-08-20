import { useRef, useState } from "react";
import { Loader2Icon, PlusIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useTemplateActions } from "@/lib/queries";

/** Add a .pptx to an asiakas's pohjat.
 *
 *  Its own component so it can sit beside the section heading, where every
 *  other "add one of these" action on the page sits, rather than inside the
 *  list it adds to.
 */
export default function TemplateUploadButton({
  customerId,
  onUploaded,
}: {
  customerId: string;
  /** Called with the new template's id. Uploading means "use this one" —
   *  otherwise the file lands in a list and nothing visibly happens, which
   *  reads as a failure. */
  onUploaded?: (templateId: string) => void;
}) {
  const actions = useTemplateActions(customerId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setBusy(true);
    try {
      const created = await actions.upload.mutateAsync(file);
      onUploaded?.(created.id);
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
    <>
      <Button disabled={busy} onClick={() => fileRef.current?.click()}>
        {busy ? (
          <Loader2Icon className="mr-2 size-4 animate-spin" />
        ) : (
          <PlusIcon className="mr-2 size-4" />
        )}
        Uusi pohja
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
    </>
  );
}
