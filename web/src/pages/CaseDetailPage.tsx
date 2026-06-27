import { useParams, useNavigate } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DatabaseIcon, FileTextIcon, ArrowLeftIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import DataTab from "@/components/DataTab";
import { useCases } from "@/lib/queries";

function ReportsPlaceholder() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-muted">
        <FileTextIcon className="size-7 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-semibold tracking-tight">Reports coming soon</h3>
      <p className="mt-2 max-w-xs text-sm text-muted-foreground leading-relaxed">
        The report wizard will be built in the next task (RX2). Upload your data
        in the Data tab to get started.
      </p>
    </div>
  );
}

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: cases } = useCases();
  const currentCase = cases?.find((c) => c.id === id);

  if (!id) return null;

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-8">
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
      <Tabs defaultValue="data" className="w-full">
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
          <ReportsPlaceholder />
        </TabsContent>
      </Tabs>
    </div>
  );
}
