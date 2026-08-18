import { useEffect, useState } from "react";
import {
  Outlet,
  NavLink,
  useLocation,
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
  SettingsIcon,
  XIcon,
  MessageSquareTextIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";

/** One customer's cases, fetched only while the group is open so opening the
 *  sidebar does not fan out a request per customer. */
function CustomerCases({ customerId }: { customerId: string }) {
  const { data: cases, isLoading } = useCustomerCases(customerId);
  const { id: activeCaseId } = useParams();

  if (isLoading) {
    return (
      <SidebarMenuSub>
        <SidebarMenuSubItem>
          <span className="px-2 text-xs text-muted-foreground">Ladataan…</span>
        </SidebarMenuSubItem>
      </SidebarMenuSub>
    );
  }

  return (
    <SidebarMenuSub>
      {/* First, not last: the action that creates the thing this group lists
          should not move down the page as the list grows. */}
      <SidebarMenuSubItem>
        <SidebarMenuSubButton
          render={<NavLink to={`/customers/${customerId}?new=case`} />}
          className="text-primary"
        >
          <PlusIcon className="size-4" />
          <span>Uusi tutkimus</span>
        </SidebarMenuSubButton>
      </SidebarMenuSubItem>

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
          <span className="px-2 text-xs text-muted-foreground">Ei vielä tutkimuksia</span>
        </SidebarMenuSubItem>
      )}
    </SidebarMenuSub>
  );
}

/** Cases created before the hierarchy existed. They belong to no customer, so
 *  they get their own group rather than a separate page — one navigation
 *  surface instead of two. Disappears once they are backfilled. */
function LegacyCasesGroup() {
  const { data: cases } = useCases();
  const { id: activeCaseId } = useParams();
  const [open, setOpen] = useState(false);

  if (!cases?.length) return null;

  return (
    <SidebarMenuItem>
      <SidebarMenuButton onClick={() => setOpen((v) => !v)} tooltip="Ilman asiakasta">
        <ChevronRightIcon
          className={`size-3.5 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
        />
        <FolderOpenIcon className="size-4" />
        <span className="truncate text-muted-foreground">Ilman asiakasta</span>
      </SidebarMenuButton>
      {open && (
        <SidebarMenuSub>
          {cases.map((c) => (
            <SidebarMenuSubItem key={c.id}>
              <SidebarMenuSubButton
                render={<NavLink to={`/cases/${c.id}`} />}
                isActive={activeCaseId === c.id}
              >
                <FolderOpenIcon className="size-4" />
                <span className="truncate">{c.name}</span>
              </SidebarMenuSubButton>
            </SidebarMenuSubItem>
          ))}
        </SidebarMenuSub>
      )}
    </SidebarMenuItem>
  );
}

/** Asiakas -> Case tree. The menu mirrors the hierarchy: a case is only
 *  reachable through the customer that owns it. */
function CustomersNav() {
  const { data: customers } = useCustomers();
  const { customerId: routeCustomerId } = useParams();
  const [openIds, setOpenIds] = useState<Record<string, boolean>>({});

  // Browsing a customer expands it, so the tree agrees with the page.
  useEffect(() => {
    if (routeCustomerId) setOpenIds((prev) => ({ ...prev, [routeCustomerId]: true }));
  }, [routeCustomerId]);

  function toggle(id: string) {
    setOpenIds((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  return (
    <SidebarMenu>
      {/* First, like "Uusi tutkimus" one level down: a create action should not
          drift down the page as the list it feeds grows. */}
      <SidebarMenuItem>
        <SidebarMenuButton
          render={<NavLink to="/customers?new=customer" />}
          tooltip="Uusi asiakas"
          className="text-primary"
        >
          <PlusIcon className="size-4" />
          <span>Uusi asiakas</span>
        </SidebarMenuButton>
      </SidebarMenuItem>

      {customers?.map((c) => {
        const open = !!openIds[c.id];
        return (
          <SidebarMenuItem key={c.id}>
            <SidebarMenuButton
              onClick={() => toggle(c.id)}
              isActive={routeCustomerId === c.id}
              tooltip={c.name}
            >
              <ChevronRightIcon
                className={`size-3.5 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
              />
              <Building2Icon className="size-4" />
              <span className="truncate">{c.name}</span>
            </SidebarMenuButton>
            {open && <CustomerCases customerId={c.id} />}
          </SidebarMenuItem>
        );
      })}

      <LegacyCasesGroup />
    </SidebarMenu>
  );
}

/** Where you actually are.
 *
 *  Derived from the route rather than hardcoded: the previous version always
 *  began with "Asiakkaat", which was a lie on the front page and on any page
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
    crumbs.push({ label: "Etusivu" });
  } else if (path.startsWith("/customers")) {
    crumbs.push({ label: "Asiakkaat", to: customerId ? "/customers" : undefined });
    const c = customers?.find((x) => x.id === customerId);
    if (c) crumbs.push({ label: c.name });
  } else if (path.startsWith("/cases/") && id) {
    crumbs.push({ label: "Asiakkaat", to: "/customers" });
    if (resolved) {
      crumbs.push({ label: resolved.customer_name, to: `/customers/${resolved.customer_id}` });
      crumbs.push({ label: resolved.name });
    } else {
      // A legacy case has no customer; say so rather than inventing one.
      crumbs.push({ label: "Ilman asiakasta" });
      crumbs.push({
        label: legacyCases?.find((c) => c.id === id)?.name ?? id,
      });
    }
    // The open report's own name, not the literal word: the crumb has to say
    // WHICH report, the same way the case crumb says which case.
    const openReport = searchParams.get("report");
    if (openReport) {
      const name = caseReports?.reports?.find((r) => r.report_id === openReport)?.name;
      crumbs.push({ label: name || "Raportti" });
    }
  }

  return (
    <nav className="flex min-w-0 items-center gap-1 text-sm text-muted-foreground">
      {crumbs.map((c, i) => (
        <span key={`${c.label}-${i}`} className="flex min-w-0 items-center gap-1">
          {i > 0 && <span className="text-muted-foreground/50 mx-0.5">/</span>}
          {c.to ? (
            <NavLink to={c.to} className="truncate transition-colors hover:text-foreground">
              {c.label}
            </NavLink>
          ) : (
            <span className="truncate font-medium text-foreground">{c.label}</span>
          )}
        </span>
      ))}
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
        title="Keskustele datasta"
      >
        <MessageSquareTextIcon className="size-4" />
        Chat
      </Button>
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

export default function AppShell() {
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
                  <SidebarMenuButton render={<NavLink to="/" end />} tooltip="Etusivu">
                    <ClockIcon className="size-4" />
                    <span>Etusivu</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          {/* The one place customers are listed. The label links to the
              management page; the tree is for getting somewhere. */}
          <SidebarGroup className="min-h-0 flex-1 overflow-y-auto group-data-[collapsible=icon]:hidden">
            <SidebarGroupLabel>
              <NavLink to="/customers" className="transition-colors hover:text-foreground">
                Asiakkaat
              </NavLink>
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <CustomersNav />
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>

        {/* Settings footer */}
        <div className="mt-auto p-2">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                render={<NavLink to="/settings" />}
                tooltip="Settings"
              >
                <SettingsIcon className="size-4" />
                <span>Settings</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </div>
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

        {/* Main content */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </SidebarInset>

    </SidebarProvider>
  );
}
