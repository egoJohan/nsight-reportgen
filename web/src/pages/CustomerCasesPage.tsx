import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { PlusIcon, FolderIcon, ArrowRightIcon, UsersIcon, LockIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCustomer,
  useCustomerCases,
  useTemplateActions,
  useTemplates,
  statusOf,
} from "@/lib/queries";
import { useSession } from "@/lib/session";
import NewCaseDialog from "@/components/NewCaseDialog";
import TemplatePicker from "@/components/TemplatePicker";
import TemplateUploadButton from "@/components/TemplateUploadButton";
import ManagePermissionsDialog from "@/components/ManagePermissionsDialog";
import NoAccessCustomer from "@/components/NoAccessCustomer";
import { RequestAccessDialog } from "@/components/RequestAccessDialog";
import type { AccessMode } from "@/lib/api";
import { EMPTY, ERROR, PAGE, PAGE_HEADER, PAGE_TITLE, ROW, SECTION_HEADER, SECTION_TITLE } from "@/lib/surfaces";

/** One customer's cases. */
export default function CustomerCasesPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const navigate = useNavigate();
  const { data: customer, isError: customerIsError, error: customerError } = useCustomer(customerId);
  const { data: cases, isLoading, isError } = useCustomerCases(customerId);
  const templates = useTemplateActions(customerId);
  // Read before the upload lands, so "was this the first?" is answerable.
  const { data: existingTemplates } = useTemplates(customerId);
  const { data: me } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [managingAccess, setManagingAccess] = useState(false);
  const [requestingPermissions, setRequestingPermissions] = useState(false);

  // A customer the caller holds no grant on 404s (spec §5, deps_auth._check)
  // — absence, not refusal, everywhere else in the app. Here alone that 404
  // gets a page instead of a dead end: NoAccessCustomer, fed by the one
  // narrow route that may still name what was refused
  // (GET /customers/{id}/name — see routes_customers.py's `customer_name`).
  const noAccess = !!customerId && customerIsError && statusOf(customerError) === 404;

  if (noAccess) {
    return (
      <div className={PAGE}>
        <NoAccessCustomer customerId={customerId!} />
      </div>
    );
  }

  // may_write on the customer (see routes_customers.py's get_customer),
  // never is_admin — see CaseDetailPage's `canEdit` for the full reasoning
  // and the courtesy/guard split. Defaults true while `customer` is still
  // loading so the common editor path renders with nothing to wait on.
  // Fail closed while the answer is in flight — see CaseDetailPage.
  const canEdit = customer?.can_edit ?? false;

  // What the "Request permissions" button offers, top right — the same slot
  // as "Manage permissions" (see PAGE_HEADER below), shown when the caller
  // is missing `edit` and hidden once they hold it. Reaching this component
  // at all means at least `view` (no grant is the `noAccess` branch above,
  // which renders NoAccessCustomer instead — so its own "Request access"
  // button and this one are never on screen together), so the only thing
  // left to ask for is `edit`. Gated on `customer` being loaded, not just
  // `!canEdit`: the fail-closed default while it's in flight would
  // otherwise flash the button for someone who turns out to already hold
  // edit.
  //
  // Never for an admin. An admin who is only a viewer really does lack
  // write access — but the answer to that is the "Manage permissions"
  // button right beside it, which they alone have and which can grant it
  // outright. Offering both put "ask someone" next to "do it yourself",
  // and the request would land in the very queue they are the one to
  // approve.
  const missingModes: AccessMode[] =
    customer && !canEdit && !me?.is_admin ? ["edit"] : [];

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

  return (
    <div className={PAGE}>
      {/* No back-link here: the shell's breadcrumb already carries the way
          back, and two of them side by side is one too many. */}
      <div className={PAGE_HEADER}>
        <h1 className={PAGE_TITLE}>{customer?.name ?? "…"}</h1>
        <div className="flex items-center gap-2">
          {/* Same top-right slot regardless of who's looking. Missing edit
              (the only gap left once this page renders at all) gets this;
              missing everything gets NoAccessCustomer's own button instead,
              never both at once — see `missingModes` above. */}
          {missingModes.length > 0 && (
            <Button variant="outline" onClick={() => setRequestingPermissions(true)}>
              <LockIcon className="mr-2 size-4" />Request permissions</Button>
          )}
          {/* Access to a customer is administered here, on the customer — not
              per-user in Settings (see the Users screen's history). Admin-only:
              a non-admin has no reason to know who else can see this customer. */}
          {me?.is_admin && (
            <Button variant="outline" onClick={() => setManagingAccess(true)}>
              <UsersIcon className="mr-2 size-4" />Manage permissions</Button>
          )}
        </div>
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

        {cases?.map((k) => {
          // Say nothing rather than "0 drafts, 0 completed" — a study with
          // no reports yet should read as empty, not as a row of zeroes.
          // Draft folds in "Empty" (no charts, no deck) along with "Draft"
          // (charts, no deck): neither is a deliverable, so this must agree
          // with the report row's own three-state badge (ReportsSection.tsx)
          // or the two pages would tell a different story about the same
          // reports — see routes_customers.py's `_report_stats`.
          const total = k.completed_reports + k.draft_reports;
          return (
            <button
              key={k.id}
              onClick={() => navigate(`/cases/${k.id}`)}
              className={ROW}
            >
              <span className="flex min-w-0 items-center gap-3">
                <FolderIcon className="size-5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 text-left">
                  <span className="block truncate font-medium">{k.name}</span>
                  {total > 0 && (
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      {k.completed_reports} completed, {k.draft_reports} draft
                      {k.draft_reports === 1 ? "" : "s"}
                    </span>
                  )}
                </span>
              </span>
              <ArrowRightIcon className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
            </button>
          );
        })}
      </div>

      {/* A study starts with a file, not with a title: the upload IS the
          create, and the name comes from the SAV's study label (or the file
          name). Asking for a name first made you invent one before you had
          seen the data, and then the real title arrived in the file anyway. */}
      {customerId && (
        <NewCaseDialog
          open={open}
          onOpenChange={setOpen}
          customerId={customerId}
          customerName={customer?.name}
        />
      )}

      {me?.is_admin && customerId && (
        <ManagePermissionsDialog
          open={managingAccess}
          onOpenChange={setManagingAccess}
          customerId={customerId}
          customerName={customer?.name ?? ""}
        />
      )}

      {customerId && missingModes.length > 0 && (
        <RequestAccessDialog
          open={requestingPermissions}
          onOpenChange={setRequestingPermissions}
          customerId={customerId}
          customerName={customer?.name ?? ""}
          allowedModes={missingModes}
        />
      )}
    </div>
  );
}
