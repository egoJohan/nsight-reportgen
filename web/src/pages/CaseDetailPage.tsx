import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DatabaseIcon, FileTextIcon, ArrowLeftIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import DataTab from "@/components/DataTab";
import ReportsTab from "@/components/ReportsTab";
import { useCases } from "@/lib/queries";

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: cases } = useCases();
  const currentCase = cases?.find((c) => c.id === id);
  const [tab, setTab] = useState("data");

  if (!id) return null;

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      {/* Back + heading */}
      <div className="mb-6">
        <Button
          variant="ghost"
          size="sm"
          className="mb-3 -ml-2 text-muted-foreground"
          onClick={() => navigate("/")}
        >
          <ArrowLeftIcon className="size-4" />
          All cases
        </Button>
        <h1 className="text-2xl font-semibold tracking-tight">
          {currentCase?.name ?? id}
        </h1>
        <p className="mt-1 text-xs text-muted-foreground font-mono">{id}</p>
      </div>

      {/* Tabs */}
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="mb-6">
          <TabsTrigger value="data" className="gap-2">
            <DatabaseIcon className="size-4" />
            Data
          </TabsTrigger>
          <TabsTrigger value="reports" className="gap-2">
            <FileTextIcon className="size-4" />
            Reports
          </TabsTrigger>
        </TabsList>

        <TabsContent value="data">
          <DataTab caseId={id} />
        </TabsContent>

        <TabsContent value="reports">
          <ReportsTab caseId={id} onGoToData={() => setTab("data")} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
