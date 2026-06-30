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
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { useCases } from "@/lib/queries";
import { useWorkspace } from "@/lib/workspace";
import NewCaseDialog from "@/components/NewCaseDialog";
import ChatPanel from "@/components/ChatPanel";
import {
  PlusIcon,
  FolderOpenIcon,
  SettingsIcon,
  XIcon,
  MessageSquareTextIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";

function CasesNav() {
  const { data: cases } = useCases();
  const { id: activeId } = useParams();

  // The active case (e.g. one just created) may be far down a long list —
  // scroll it into view so it's visibly selected, not hidden below the fold.
  useEffect(() => {
    if (!activeId) return;
    const el = document.querySelector(`a[href="/cases/${activeId}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [activeId, cases]);

  // Newest case first (descending): the backend returns cases in creation
  // order, so reverse to put the most recent at the top.
  const ordered = (cases ?? []).slice().reverse();

  return (
    <SidebarMenu>
      {ordered.map((c) => (
        <SidebarMenuItem key={c.id}>
          <SidebarMenuButton
            render={<NavLink to={`/cases/${c.id}`} />}
            isActive={activeId === c.id}
            tooltip={c.name}
          >
            <FolderOpenIcon className="size-4" />
            <span className="truncate">{c.name}</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      ))}
    </SidebarMenu>
  );
}

function Breadcrumb() {
  const location = useLocation();
  const { data: cases } = useCases();
  const { id } = useParams();

  const currentCase = id ? cases?.find((c) => c.id === id) : null;
  const onCasePage = location.pathname.startsWith("/cases/");

  return (
    <nav className="flex items-center gap-1 text-sm text-muted-foreground">
      <NavLink to="/" className="hover:text-foreground transition-colors">
        Cases
      </NavLink>
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
  const [newCaseOpen, setNewCaseOpen] = useState(false);
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
          {/* New case — opens the upload dialog (creation = upload). */}
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    onClick={() => setNewCaseOpen(true)}
                    tooltip="New case"
                    className="font-medium text-primary"
                  >
                    <PlusIcon className="size-4" />
                    <span>New case</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          {/* Cases list — own scroll region (visible scrollbar) so a long list
              is reachable while "New case" stays pinned above. */}
          <SidebarGroup className="min-h-0 flex-1 overflow-y-auto group-data-[collapsible=icon]:hidden">
            <SidebarGroupContent>
              <CasesNav />
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

      <NewCaseDialog open={newCaseOpen} onOpenChange={setNewCaseOpen} />
    </SidebarProvider>
  );
}
