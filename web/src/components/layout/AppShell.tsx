import { useEffect, useState } from "react";
import {
  Outlet,
  NavLink,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  SidebarProvider,
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarInset,
  SidebarTrigger,
  SidebarMenuSub,
  SidebarMenuSubItem,
  SidebarMenuSubButton,
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import {
  useCases,
  useCustomers,
  useCustomerNames,
  useCustomerCases,
  useResolvedCase,
  useCaseReports,
} from "@/lib/queries";
import { useWorkspace } from "@/lib/workspace";
import ChatPanel from "@/components/ChatPanel";
import {
  PlusIcon,
  FolderOpenIcon,
  Building2Icon,
  ChevronRightIcon,
  ClockIcon,
  LockIcon,
  SettingsIcon,
  XIcon,
  MessageSquareTextIcon,
  LogOutIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import TiledBackdrop from "@/components/layout/TiledBackdrop";
import { useSession, signOut, type Me } from "@/lib/session";

/** One customer's cases, fetched only while the group is open so opening the
 *  sidebar does not fan out a request per customer. */
function CustomerCases({ customerId, canEdit }: { customerId: string; canEdit: boolean }) {
  const { data: cases, isLoading } = useCustomerCases(customerId);
  const { id: activeCaseId } = useParams();

  if (isLoading) {
    return (
      <SidebarMenuSub>
        <SidebarMenuSubItem>
          <span className="px-2 text-xs text-muted-foreground">Loading…</span>
        </SidebarMenuSubItem>
      </SidebarMenuSub>
    );
  }

  return (
    <SidebarMenuSub>
      {/* First, not last: the action that creates the thing this group lists
          should not move down the page as the list grows. Creating a study
          is a write against the customer (see CustomerCasesPage's canEdit) —
          a viewer gets no link for it. */}
      {canEdit && (
        <SidebarMenuSubItem>
          <SidebarMenuSubButton
            render={<NavLink to={`/customers/${customerId}?new=case`} />}
            className="text-primary"
          >
            <PlusIcon className="size-4" />
            <span>New study</span>
          </SidebarMenuSubButton>
        </SidebarMenuSubItem>
      )}

      {cases?.map((k) => (
        <SidebarMenuSubItem key={k.id}>
          <SidebarMenuSubButton
            render={<NavLink to={`/cases/${k.id}`} />}
            isActive={activeCaseId === k.id}
          >
            <FolderOpenIcon className="size-4" />
            <span className="truncate">{k.name}</span>
          </SidebarMenuSubButton>
        </SidebarMenuSubItem>
      ))}

      {cases?.length === 0 && (
        <SidebarMenuSubItem>
          <span className="px-2 text-xs text-muted-foreground">No studies yet</span>
        </SidebarMenuSubItem>
      )}
    </SidebarMenuSub>
  );
}

/** Asiakas -> Case tree. The menu mirrors the hierarchy: a case is only
 *  reachable through the customer that owns it. */
function CustomersNav() {
  const { data: customers } = useCustomers();
  const { data: allNames } = useCustomerNames();
  const { customerId: routeCustomerId } = useParams();
  const [openIds, setOpenIds] = useState<Record<string, boolean>>({});

  // Deliberately NOT expanding on navigation. Folding is the chevron's job and
  // nothing else's: opening a customer used to force its subtree open, so
  // clicking the name both navigated AND unfolded, which is indistinguishable
  // from the old fold-on-label-click it replaced.

  function toggle(id: string) {
    setOpenIds((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  return (
    <SidebarMenu>
      {/* First, like "New study" one level down: a create action should not
          drift down the page as the list it feeds grows. */}
      <SidebarMenuItem>
        <SidebarMenuButton
          render={<NavLink to="/customers?new=customer" />}
          tooltip="New customer"
          className="text-primary"
        >
          <PlusIcon className="size-4" />
          <span>New customer</span>
        </SidebarMenuButton>
      </SidebarMenuItem>

      {customers?.map((c) => {
        const open = !!openIds[c.id];
        return (
          <SidebarMenuItem key={c.id}>
            {/* The label navigates; only the chevron folds. Clicking a
                customer's NAME and getting a fold instead of that customer's
                page is the kind of thing you re-learn every time you use it —
                the disclosure triangle is the affordance for disclosure. */}
            <SidebarMenuButton
              render={<NavLink to={`/customers/${c.id}`} />}
              isActive={routeCustomerId === c.id}
              tooltip={c.name}
            >
              <button
                type="button"
                aria-label={open ? `Collapse ${c.name}` : `Expand ${c.name}`}
                className="-m-1 shrink-0 rounded p-1 hover:bg-accent"
                onClick={(e) => {
                  // The row is a link; the chevron must not follow it.
                  e.preventDefault();
                  e.stopPropagation();
                  toggle(c.id);
                }}
              >
                <ChevronRightIcon
                  className={`size-3.5 transition-transform ${open ? "rotate-90" : ""}`}
                />
              </button>
              <Building2Icon className="size-4" />
              <span className="truncate">{c.name}</span>
            </SidebarMenuButton>
            {open && <CustomerCases customerId={c.id} canEdit={c.can_edit} />}
          </SidebarMenuItem>
        );
      })}

      {/* Customers this user cannot open. Listed deliberately: without them
          there is no way to FIND a customer to ask about, and the request flow
          is unreachable. They carry no chevron (there is nothing to expand)
          and lead to the no-access page, which is where the asking happens.
          Only id and name are known here — see api.customers.listNames. */}
      {(allNames ?? [])
        .filter((n) => !(customers ?? []).some((c) => c.id === n.id))
        .map((n) => (
          <SidebarMenuItem key={n.id}>
            <SidebarMenuButton
              render={<NavLink to={`/customers/${n.id}`} />}
              isActive={routeCustomerId === n.id}
              tooltip={`${n.name} — no access`}
              className="text-muted-foreground"
            >
              <LockIcon className="size-3.5 shrink-0 opacity-70" />
              <Building2Icon className="size-4" />
              <span className="truncate">{n.name}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        ))}
    </SidebarMenu>
  );
}

/** Where you actually are.
 *
 *  Derived from the route rather than hardcoded: the previous version always
 *  began with "Customers", which was a lie on the front page and on any page
 *  outside the customer tree. */
function Breadcrumb() {
  const location = useLocation();
  const { id, customerId } = useParams();
  const [searchParams] = useSearchParams();
  const { data: customers } = useCustomers();
  const { data: resolved } = useResolvedCase(id);
  const { data: legacyCases } = useCases();
  const { data: caseReports } = useCaseReports(id ?? null);

  const crumbs: { label: string; to?: string }[] = [];
  const path = location.pathname;

  if (path === "/") {
    crumbs.push({ label: "Home" });
  } else if (path.startsWith("/customers")) {
    crumbs.push({ label: "Customers", to: "/customers" });
    const c = customers?.find((x) => x.id === customerId);
    if (c) crumbs.push({ label: c.name, to: `/customers/${customerId}` });
  } else if (path.startsWith("/cases/") && id) {
    crumbs.push({ label: "Customers", to: "/customers" });
    if (resolved) {
      crumbs.push({ label: resolved.customer_name, to: `/customers/${resolved.customer_id}` });
      // Linked WITHOUT the ?report= param, which is how you leave an open
      // report: with a report open this crumb is the way back to the case, and
      // it used to be dead text with no other route out.
      crumbs.push({ label: resolved.name, to: `/cases/${id}` });
    } else {
      // A legacy case has no customer; say so rather than inventing one.
      crumbs.push({ label: "No customer" });
      crumbs.push({
        label: legacyCases?.find((c) => c.id === id)?.name ?? id,
        to: `/cases/${id}`,
      });
    }
    // The open report's own name, not the literal word: the crumb has to say
    // WHICH report, the same way the case crumb says which case.
    const openReport = searchParams.get("report");
    if (openReport) {
      const name = caseReports?.reports?.find((r) => r.report_id === openReport)?.name;
      crumbs.push({ label: name || "Report" });
    }
  }

  // Every crumb but the last is a way back — the last one is where you are, so
  // it stays plain whatever `to` it carries. Deciding it here rather than when
  // the crumbs are built is what stops a newly added crumb from silently
  // stranding the one above it.
  return (
    <nav className="flex min-w-0 items-center gap-1 text-sm text-muted-foreground">
      {crumbs.map((c, i) => {
        const here = i === crumbs.length - 1;
        return (
          <span key={`${c.label}-${i}`} className="flex min-w-0 items-center gap-1">
            {i > 0 && <span className="text-muted-foreground/50 mx-0.5">/</span>}
            {c.to && !here ? (
              <NavLink to={c.to} className="truncate transition-colors hover:text-foreground">
                {c.label}
              </NavLink>
            ) : (
              <span className="truncate font-medium text-foreground">{c.label}</span>
            )}
          </span>
        );
      })}
    </nav>
  );
}

// Right-aligned close (X) on the top-bar row, shown only while a report is open
// (?report=<id>). Clearing the param returns to the case's report list.
// Persistent "Chat" launcher in the top bar — always present (rightmost) while a
// case with data is selected, so it's available both in the case view and while a
// report is open. Reads the case id from the route and its material from the
// workspace; the panel is a fixed overlay.
function ChatLauncher() {
  const { pathname } = useLocation();
  const match = pathname.match(/^\/cases\/([^/]+)/);
  const caseId = match ? match[1] : null;
  const { workspace } = useWorkspace(caseId ?? "");
  const materialId = caseId ? workspace.materialId : null;
  const [open, setOpen] = useState(false);
  if (!caseId || !materialId) return null;
  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="text-muted-foreground"
        onClick={() => setOpen(true)}
        title="Chat with the data"
      >
        <MessageSquareTextIcon className="size-4" />Chat</Button>
      <ChatPanel materialId={materialId} open={open} onClose={() => setOpen(false)} />
    </>
  );
}

function CloseReportButton() {
  const [searchParams, setSearchParams] = useSearchParams();
  if (!searchParams.get("report")) return null;
  return (
    <Button
      variant="ghost"
      size="sm"
      className="text-muted-foreground"
      onClick={() =>
        setSearchParams(
          (prev) => {
            const next = new URLSearchParams(prev);
            next.delete("report");
            return next;
          },
          { replace: true }
        )
      }
    >
      <XIcon className="size-4" />
      Close report
    </Button>
  );
}

/** Who is signed in, and the one way out. Shown, not hidden behind a menu —
 *  a session that outlives the person who opened it is exactly the kind of
 *  thing that should be visible at a glance. */
function UserFooter({ me }: { me: Me }) {
  const [busy, setBusy] = useState(false);

  async function handleSignOut() {
    setBusy(true);
    try {
      await signOut();
    } finally {
      // A hard navigation, not react-router's `navigate()`: this component
      // is still mounted with the pre-sign-out `me` while the request is in
      // flight, so a client-side navigate here races AppShell's own guard
      // effect — which also fires once the session query settles to null
      // while AppShell is still on the old route, and can re-add its own
      // `?next=` back onto the very page being signed out of. `location
      // .assign` sidesteps the race by dropping the whole SPA and starting
      // over, the same reasoning api.ts's 401 handler already relies on.
      location.assign("/login");
    }
  }

  return (
    <div className="mt-auto space-y-1 p-2">
      <div className="flex items-center gap-2 px-2 py-1 group-data-[collapsible=icon]:justify-center">
        <div
          className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-medium text-primary-foreground"
          title={me.email}
        >
          {(me.name || me.email).slice(0, 1).toUpperCase()}
        </div>
        <p className="min-w-0 truncate text-xs font-medium group-data-[collapsible=icon]:hidden">
          {me.name || me.email}
        </p>
      </div>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton render={<NavLink to="/settings" />} tooltip="Settings">
            <SettingsIcon className="size-4" />
            <span>Settings</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton onClick={handleSignOut} disabled={busy} tooltip="Sign out">
            <LogOutIcon className="size-4" />
            <span>Sign out</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </div>
  );
}

export default function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: me, isLoading: sessionLoading } = useSession();

  useEffect(() => {
    if (!sessionLoading && me === null) {
      const next = encodeURIComponent(location.pathname + location.search);
      navigate(`/login?next=${next}`, { replace: true });
    }
  }, [sessionLoading, me, location.pathname, location.search, navigate]);

  if (sessionLoading || !me) {
    // Avoids a flash of the shell (and of every page's own data fetches)
    // before the redirect above fires. `!me` rather than `me === null`
    // narrows out `undefined` too, so `me` below is a plain `Me`.
    return null;
  }

  return (
    <SidebarProvider>
      <Sidebar variant="sidebar" collapsible="icon">
        {/* Logo — the mark is white, so sit it on a dark brand band. */}
        <SidebarHeader className="px-3 py-4">
          <NavLink
            to="/"
            className="flex items-center justify-center rounded-xl bg-primary px-5 py-4 group-data-[collapsible=icon]:hidden"
          >
            <img src="/nsight-logo.svg" alt="nSight" className="h-12 w-auto" />
          </NavLink>
        </SidebarHeader>

        <SidebarContent>
          {/* The front page is a destination like any other, so it lives in the
              nav rather than being reachable only via the logo. */}
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton render={<NavLink to="/" end />} tooltip="Home">
                    <ClockIcon className="size-4" />
                    <span>Home</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          {/* The one place customers are listed. The label links to the
              management page; the tree is for getting somewhere. */}
          <SidebarGroup className="min-h-0 flex-1 overflow-y-auto group-data-[collapsible=icon]:hidden">
            <SidebarGroupLabel>
              <NavLink to="/customers" className="transition-colors hover:text-foreground">Customers</NavLink>
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <CustomersNav />
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>

        {/* Settings + who is signed in, with the way out. `me` is never null
            here — the guard above returns before this renders otherwise. */}
        <UserFooter me={me} />
      </Sidebar>

      <SidebarInset>
        {/* Top bar */}
        <header className="flex h-14 items-center gap-3 border-b bg-background px-4 shrink-0">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="h-4" />
          <Breadcrumb />
          {/* Right side: Close report (left) then Chat (always rightmost). */}
          <div className="ml-auto flex items-center gap-2">
            <CloseReportButton />
            <ChatLauncher />
          </div>
        </header>

        {/* Main content. `relative isolate` is what makes the backdrop's
            negative z-index resolve against THIS pane instead of sliding
            behind the shell's own background. */}
        <main className="relative isolate flex-1 overflow-auto">
          <TiledBackdrop />
          <Outlet />
        </main>
      </SidebarInset>

    </SidebarProvider>
  );
}
