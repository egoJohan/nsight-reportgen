import { Routes, Route } from "react-router-dom";
import AppShell from "@/components/layout/AppShell";
import CasesPage from "@/pages/CasesPage";
import CaseDetailPage from "@/pages/CaseDetailPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<CasesPage />} />
        <Route path="/cases/:id" element={<CaseDetailPage />} />
      </Route>
    </Routes>
  );
}
