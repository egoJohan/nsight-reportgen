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
import { useCases, useCustomers, useCustomerCases } from "@/lib/queries";
import { useWorkspace } from "@/lib/workspace";
import ChatPanel from "@/components/ChatPanel";
import TiledBackdrop from "@/components/layout/TiledBackdrop";
import {
  PlusIcon,
  FolderOpenIcon,
  Building2Icon,
  ChevronRightIcon,
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
          <span className="px-2 text-xs text-muted-foreground">Ei vielä caseja</span>
        </SidebarMenuSubItem>
      )}

      {/* Adding a case belongs to the customer it lands under, so the action
          lives inside the group rather than as a global button. */}
      <SidebarMenuSubItem>
        <SidebarMenuSubButton
          render={<NavLink to={`/customers/${customerId}?new=case`} />}
          className="text-primary"
        >
          <PlusIcon className="size-4" />
          <span>Uusi case</span>
        </SidebarMenuSubButton>
      </SidebarMenuSubItem>
    </SidebarMenuSub>
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

      {customers?.length === 0 && (
        <SidebarMenuItem>
          <span className="px-2 text-xs text-muted-foreground">Ei vielä asiakkaita</span>
        </SidebarMenuItem>
      )}
    </SidebarMenu>
  );
}

function Breadcrumb() {
  const location = useLocation();
  const { data: cases } = useCases();
  const { data: customers } = useCustomers();
  const { id, customerId } = useParams();

  const currentCase = id ? cases?.find((c) => c.id === id) : null;
  const currentCustomer = customerId ? customers?.find((c) => c.id === customerId) : null;
  const onCasePage = location.pathname.startsWith("/cases/");

  return (
    <nav className="flex items-center gap-1 text-sm text-muted-foreground">
      <NavLink to="/customers" className="hover:text-foreground transition-colors">
        Asiakkaat
      </NavLink>
      {currentCustomer && (
        <>
          <span className="text-muted-foreground/50 mx-0.5">/</span>
          <span className="text-foreground font-medium">{currentCustomer.name}</span>
        </>
      )}
      {onCasePage && currentCase && (
        <>
          <span className="text-muted-foreground/50 mx-0.5">/</span>
          <span className="text-foreground font-medium">{currentCase.name}</span>
        </>
      )}
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
          {/* A case is created under a customer, so the top-level action is
              adding a CUSTOMER; "Uusi case" lives inside each customer group. */}
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    render={<NavLink to="/customers?new=customer" />}
                    tooltip="Uusi asiakas"
                    className="font-medium text-primary"
                  >
                    <PlusIcon className="size-4" />
                    <span>Uusi asiakas</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          {/* Asiakas -> Case tree — own scroll region so a long list stays
              reachable while "Uusi asiakas" stays pinned above. */}
          <SidebarGroup className="min-h-0 flex-1 overflow-y-auto group-data-[collapsible=icon]:hidden">
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

      <SidebarInset className="isolate">
        {/* Behind every page. `isolate` above keeps the -z layer from sliding
            behind an opaque ancestor. */}
        <TiledBackdrop />

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
