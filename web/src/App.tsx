import { Routes, Route } from "react-router-dom";
import NotFoundPage from "@/pages/NotFoundPage";
import AppShell from "@/components/layout/AppShell";
import LoginPage from "@/pages/LoginPage";
import RequestAccessPage from "@/pages/RequestAccessPage";
import RecentReportsPage from "@/pages/RecentReportsPage";
import CustomersPage from "@/pages/CustomersPage";
import CustomerCasesPage from "@/pages/CustomerCasesPage";
import CaseDetailPage from "@/pages/CaseDetailPage";
import SettingsPage from "@/pages/SettingsPage";

export default function App() {
  return (
    <Routes>
      {/* Outside AppShell: signing in has no sidebar, no breadcrumb, nothing
          that assumes a session already exists. */}
      <Route path="/login" element={<LoginPage />} />
      {/* Outside AppShell, like /login: whoever lands here has no account, so
          the shell's own guard would bounce them straight back to sign-in. */}
      <Route path="/request-access" element={<RequestAccessPage />} />
      <Route element={<AppShell />}>
        {/* The landing page answers "where was I?" — the customer tree is
            navigation and lives in the sidebar. */}
        <Route index element={<RecentReportsPage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/customers/:customerId" element={<CustomerCasesPage />} />
        {/* Pre-hierarchy cases are reachable from the sidebar's "Ilman
            asiakasta" group; only the detail route is still needed. */}
        <Route path="/cases/:id" element={<CaseDetailPage />} />
        {/* The sidebar has linked here all along; this is the page. */}
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      {/* Anything else, OUTSIDE the shell: a wrong address is not a page of the
          app, and framing it in the sidebar and breadcrumb of a section the
          user never reached reads as "this section is broken" rather than
          "that link is wrong". Full screen, with one way back. */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
