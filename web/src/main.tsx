import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./index.css";
import App from "./App";
import { MaintenanceScreen } from "@/components/MaintenanceScreen";
import { installFetchProbe } from "@/lib/serviceHealth";

// Before anything fetches: the very first request of a cold load is the
// session check, and it must be able to raise the maintenance screen too.
installFetchProbe();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

// The cache, reachable from the console. The preview queue and the components
// that display its work are keyed on the same fingerprints, and the failure
// that is hardest to see is the two disagreeing — so both halves can be
// inspected: window.__previewQueue.state() and window.__qc.getQueryCache().
if (typeof window !== "undefined") {
  (window as unknown as { __qc?: QueryClient }).__qc = queryClient;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <TooltipProvider>
          <App />
          {/* Over everything: while the hive is away almost every query fails,
              and one honest screen is better than a broken page behind a stack
              of identical toasts. It removes itself when the hive returns. */}
          <MaintenanceScreen />
          <Toaster position="bottom-right" richColors />
        </TooltipProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>
);
