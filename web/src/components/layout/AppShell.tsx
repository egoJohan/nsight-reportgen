import { useEffect, useState } from "react";
import { Outlet, NavLink, useLocation, useParams } from "react-router-dom";
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
import NewCaseDialog from "@/components/NewCaseDialog";
import {
  PlusIcon,
  FolderOpenIcon,
  SettingsIcon,
  BarChart3Icon,
} from "lucide-react";

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

  return (
    <SidebarMenu>
      {(cases ?? []).map((c) => (
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

export default function AppShell() {
  const [newCaseOpen, setNewCaseOpen] = useState(false);
  return (
    <SidebarProvider>
      <Sidebar variant="sidebar" collapsible="icon">
        {/* Wordmark */}
        <SidebarHeader className="px-4 py-5">
          <div className="flex items-center gap-2.5">
            <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground shrink-0">
              <BarChart3Icon className="size-4" />
            </div>
            <span className="font-semibold text-base tracking-tight group-data-[collapsible=icon]:hidden">
              nSight
            </span>
          </div>
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

          {/* Cases list */}
          <SidebarGroup className="group-data-[collapsible=icon]:hidden">
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
