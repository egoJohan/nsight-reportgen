import { useRef, useState } from "react";
import { toast } from "sonner";
import {
  UploadCloudIcon,
  SearchIcon,
  AlertCircleIcon,
  DatabaseIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useQuestions, useUploadMaterial } from "@/lib/queries";
import type { Question } from "@/lib/api";

// ---- Sort options ----
type SortKey = "default" | "text_asc" | "text_desc" | "kind";

function sortQuestions(questions: Question[], sort: SortKey): Question[] {
  const q = [...questions];
  if (sort === "text_asc") q.sort((a, b) => a.text.localeCompare(b.text));
  if (sort === "text_desc") q.sort((a, b) => b.text.localeCompare(a.text));
  if (sort === "kind") q.sort((a, b) => a.kind.localeCompare(b.kind));
  return q;
}

// ---- Kind badge ----
function KindBadge({ q }: { q: Question }) {
  if (q.kind === "multi") {
    return (
      <Badge variant="secondary" className="whitespace-nowrap font-normal">
        Multi · {q.variables.length}
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="whitespace-nowrap font-normal">
      Single
    </Badge>
  );
}

// ---- Question table ----
function QuestionTable({
  materialId,
}: {
  materialId: string;
}) {
  const { data: questions, isLoading, isError } = useQuestions(materialId);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("default");

  if (isLoading) {
    return (
      <div className="space-y-2 pt-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError || !questions) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-4 text-sm text-destructive mt-4">
        <AlertCircleIcon className="size-4 shrink-0" />
        Failed to load questions.
      </div>
    );
  }

  const filtered = questions.filter((q) =>
    q.text.toLowerCase().includes(search.toLowerCase())
  );
  const sorted = sortQuestions(filtered, sort);

  return (
    <div className="mt-6">
      {/* Toolbar */}
      <div className="mb-4 flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
          <Input
            placeholder="Search questions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={sort} onValueChange={(v) => setSort(v as SortKey)}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Sort by…" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="default">Default order</SelectItem>
            <SelectItem value="text_asc">A → Z</SelectItem>
            <SelectItem value="text_desc">Z → A</SelectItem>
            <SelectItem value="kind">By type</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground tabular-nums ml-auto shrink-0">
          {sorted.length} / {questions.length} questions
        </span>
      </div>

      {sorted.length === 0 ? (
        <div className="py-16 text-center text-sm text-muted-foreground">
          No questions match your search.
        </div>
      ) : (
        <div className="rounded-xl border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="w-full py-3">Question</TableHead>
                <TableHead className="whitespace-nowrap py-3">Type</TableHead>
                <TableHead className="whitespace-nowrap py-3">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((q) => (
                <TableRow key={q.qid} className="group">
                  <TableCell className="py-3 max-w-0">
                    <p className="text-sm leading-snug line-clamp-2 group-hover:line-clamp-none transition-all">
                      {q.text}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground font-mono">
                      {q.qid}
                    </p>
                  </TableCell>
                  <TableCell className="py-3 align-top">
                    <KindBadge q={q} />
                  </TableCell>
                  <TableCell className="py-3 align-top">
                    {q.missing_values && q.missing_values.length > 0 ? (
                      <Badge
                        variant="outline"
                        className="text-amber-600 border-amber-300 bg-amber-50 whitespace-nowrap font-normal"
                      >
                        Not answered
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground/60">—</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

// ---- Upload area ----
function UploadArea({
  caseId,
  onUploaded,
}: {
  caseId: string;
  onUploaded: (materialId: string, questionCount: number) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadMaterial(caseId);

  function handleFile(file: File) {
    if (!file.name.match(/\.(sav|zsav)$/i)) {
      toast.error("Please upload a .sav or .zsav SPSS file");
      return;
    }
    upload.mutate(file, {
      onSuccess: (res) => {
        toast.success(
          `Uploaded — ${res.question_count} questions curated`
        );
        onUploaded(res.material_id, res.question_count);
      },
      onError: (err) => {
        toast.error(`Upload failed: ${err.message}`);
      },
    });
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      className="relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-border bg-muted/30 px-8 py-12 text-center transition-colors hover:border-primary/50 hover:bg-muted/50"
    >
      <div className="mb-4 flex size-12 items-center justify-center rounded-xl bg-background shadow-sm">
        <UploadCloudIcon className="size-6 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium">
        {upload.isPending ? "Uploading…" : "Drop your SPSS file here"}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        .sav or .zsav — or{" "}
        <button
          type="button"
          className="underline underline-offset-2 hover:text-foreground transition-colors"
          onClick={() => inputRef.current?.click()}
          disabled={upload.isPending}
        >
          browse to choose
        </button>
      </p>
      <input
        ref={inputRef}
        type="file"
        accept=".sav,.zsav"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = "";
        }}
      />
      {upload.isPending && (
        <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-background/80 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-2">
            <div className="size-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <p className="text-xs text-muted-foreground">Processing…</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ---- Main DataTab ----
export default function DataTab({ caseId }: { caseId: string }) {
  const [materialId, setMaterialId] = useState<string | null>(null);

  return (
    <div>
      {!materialId ? (
        <>
          <div className="mb-6">
            <h3 className="text-base font-semibold">Data source</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Upload an SPSS file to extract and browse the curated questions.
            </p>
          </div>
          <UploadArea
            caseId={caseId}
            onUploaded={(id) => setMaterialId(id)}
          />
        </>
      ) : (
        <>
          <div className="mb-2 flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold">Questions</h3>
              <p className="mt-0.5 text-sm text-muted-foreground flex items-center gap-1.5">
                <DatabaseIcon className="size-3.5" />
                <span className="font-mono text-xs">{materialId}</span>
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setMaterialId(null)}
              className="text-muted-foreground"
            >
              Replace file
            </Button>
          </div>
          <QuestionTable materialId={materialId} />
        </>
      )}
    </div>
  );
}
