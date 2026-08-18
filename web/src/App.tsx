import { Routes, Route } from "react-router-dom";
import AppShell from "@/components/layout/AppShell";
import CustomersPage from "@/pages/CustomersPage";
import CustomerCasesPage from "@/pages/CustomerCasesPage";
import CasesPage from "@/pages/CasesPage";
import CaseDetailPage from "@/pages/CaseDetailPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        {/* Asiakas is the navigation root: a case belongs to exactly one. */}
        <Route index element={<CustomersPage />} />
        <Route path="/customers/:customerId" element={<CustomerCasesPage />} />
        {/* Kept while the pre-hierarchy cases are backfilled under a customer,
            so existing links and those 37 cases still resolve. */}
        <Route path="/cases" element={<CasesPage />} />
        <Route path="/cases/:id" element={<CaseDetailPage />} />
      </Route>
    </Routes>
  );
}
