import { Routes, Route } from "react-router-dom";
import AppShell from "@/components/layout/AppShell";
import LoginPage from "@/pages/LoginPage";
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
    </Routes>
  );
}
