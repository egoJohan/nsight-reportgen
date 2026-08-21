import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { PlusIcon, FolderIcon, ArrowRightIcon, UsersIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  useCustomer,
  useCustomerCases,
  useCreateCustomerCase,
  useTemplateActions,
  useTemplates,
} from "@/lib/queries";
import { useSession } from "@/lib/session";
import TemplatePicker from "@/components/TemplatePicker";
import TemplateUploadButton from "@/components/TemplateUploadButton";
import ManagePermissionsDialog from "@/components/ManagePermissionsDialog";
import { EMPTY, ERROR, PAGE, PAGE_HEADER, PAGE_TITLE, ROW, SECTION_HEADER, SECTION_TITLE } from "@/lib/surfaces";

/** One customer's cases. */
export default function CustomerCasesPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const navigate = useNavigate();
  const { data: customer } = useCustomer(customerId);
  const { data: cases, isLoading, isError } = useCustomerCases(customerId);
  const createCase = useCreateCustomerCase(customerId);
  const templates = useTemplateActions(customerId);
  // Read before the upload lands, so "was this the first?" is answerable.
  const { data: existingTemplates } = useTemplates(customerId);
  const { data: me } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [name, setName] = useState("");
  const [managingAccess, setManagingAccess] = useState(false);

  // may_write on the customer (see routes_customers.py's get_customer),
  // never is_admin — see CaseDetailPage's `canEdit` for the full reasoning
  // and the courtesy/guard split. Defaults true while `customer` is still
  // loading so the common editor path renders with nothing to wait on.
  const canEdit = customer?.can_edit ?? true;

  // Reached from the sidebar's per-customer "Uusi case" link. Gated on
  // canEdit too: hiding the button does not stop someone opening this URL
  // directly, and a create dialog that can only ever 403 has no reason to
  // open.
  const open = canEdit && searchParams.get("new") === "case";
  function setOpen(next: boolean) {
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (next) p.set("new", "case");
        else p.delete("new");
        return p;
      },
      { replace: true }
    );
  }

  async function submit() {
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      const created = await createCase.mutateAsync(trimmed);
      setOpen(false);
      setName("");
      navigate(`/cases/${created.id}`);
    } catch {
      toast.error("Could not create the study");
    }
  }

  return (
    <div className={PAGE}>
      {/* No back-link here: the shell's breadcrumb already carries the way
          back, and two of them side by side is one too many. */}
      <div className={PAGE_HEADER}>
        <h1 className={PAGE_TITLE}>{customer?.name ?? "…"}</h1>
        {/* Access to a customer is administered here, on the customer — not
            per-user in Settings (see the Users screen's history). Admin-only:
            a non-admin has no reason to know who else can see this customer. */}
        {me?.is_admin && (
          <Button variant="outline" onClick={() => setManagingAccess(true)}>
            <UsersIcon className="mr-2 size-4" />Manage permissions</Button>
        )}
      </div>

      {/* Its own section, headed like "Studies" below: the pohjat belong to
          the asiakas, and every tutkimus under it picks from this list.
          Editor-only: uploading, and picking a row (which BINDS it — a
          write), are both writes against the customer. */}
      {customerId && canEdit && (
        <>
          {/* Each section's "add one of these" sits beside its own heading, so
              a page with two lists has no single button whose target you have
              to work out. */}
          <div className={SECTION_HEADER}>
            <h2 className={SECTION_TITLE}>Templates</h2>
            <TemplateUploadButton
              customerId={customerId}
              // The FIRST one becomes the asiakas's pohja, so a customer set
              // up in one step has a selected default and the list shows which
              // it is. A later upload is an addition, not a decision — binding
              // every upload silently re-pointed every new report at whichever
              // file happened to be added last.
              onUploaded={(id) => {
                if (!existingTemplates?.length) templates.bindCustomer.mutate(id);
              }}
            />
          </div>
          <div className="mt-3">
            <TemplatePicker
              customerId={customerId}
              currentId={customer?.template_id ?? ""}
              manageLibrary
              onBind={(id) => templates.bindCustomer.mutate(id)}
            />
          </div>
        </>
      )}

      {/* SECTION_TITLE, the same as "Reports" on the tutkimus page: this
          divides the page, it is not a muted label inside a dialog. */}
      <div className={SECTION_HEADER}>
        <h2 className={SECTION_TITLE}>Studies</h2>
        {/* Creating a study is a write against the customer — a viewer gets
            no button for it. */}
        {canEdit && (
          <Button variant="outline" onClick={() => setOpen(true)}>
            <PlusIcon className="mr-2 size-4" />New study</Button>
        )}
      </div>

      <div className="mt-3 space-y-2">
        {isLoading && [0, 1].map((i) => <Skeleton key={i} className="h-16 w-full" />)}

        {isError && (
          <p className={ERROR}>Could not load the studies.</p>
        )}

        {cases?.length === 0 && (
          <div className={EMPTY}>
            <FolderIcon className="mx-auto size-8 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">This customer has no studies yet.</p>
          </div>
        )}

        {cases?.map((k) => (
          <button
            key={k.id}
            onClick={() => navigate(`/cases/${k.id}`)}
            className={ROW}
          >
            <span className="flex items-center gap-3">
              <FolderIcon className="size-5 text-muted-foreground" />
              <span className="font-medium">{k.name}</span>
            </span>
            <ArrowRightIcon className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
          </button>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New study</DialogTitle>
            <DialogDescription>
              Tutkimus kuuluu asiakkaaseen {customer?.name}.
            </DialogDescription>
          </DialogHeader>
          <Input
            autoFocus
            value={name}
            placeholder="Study name"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submit} disabled={!name.trim() || createCase.isPending}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {me?.is_admin && customerId && (
        <ManagePermissionsDialog
          open={managingAccess}
          onOpenChange={setManagingAccess}
          customerId={customerId}
          customerName={customer?.name ?? ""}
        />
      )}
    </div>
  );
}
