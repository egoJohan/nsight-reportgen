import { useNavigate } from "react-router-dom";
import { FileTextIcon, ArrowRightIcon, Building2Icon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useRecentReports, useCustomers } from "@/lib/queries";
import { ROW, EMPTY, ERROR } from "@/lib/surfaces";

/** Relative time, in Finnish, at the granularity a report list actually needs.
 *  An exact timestamp is noise here — "3 päivää sitten" answers the question
 *  the list is asked ("what was I last working on?"). */
function since(iso: string): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "juuri nyt";
  if (mins < 60) return `${mins} min sitten`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} h sitten`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} pv sitten`;
  return new Date(iso).toLocaleDateString("fi-FI");
}

/** The landing page: what you were last working on.
 *
 *  Reports rather than customers, because a customer list is navigation and
 *  the front page should answer "where was I?". Customers stay one click away
 *  in the sidebar tree. */
export default function RecentReportsPage() {
  const navigate = useNavigate();
  const { data: reports, isLoading, isError } = useRecentReports(10);
  const { data: customers } = useCustomers();

  const customerName = (id: string) =>
    customers?.find((c) => c.id === id)?.name ?? "";

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-12">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Viimeisimmät raportit</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Kymmenen viimeksi muokattua raporttia, uusin ensin.
          </p>
        </div>
        <Button variant="outline" onClick={() => navigate("/customers")}>
          <Building2Icon className="mr-2 size-4" />
          Asiakkaat
        </Button>
      </div>

      <div className="mt-8 space-y-2">
        {isLoading && [0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}

        {isError && (
          <p className={ERROR}>
            Raporttien haku epäonnistui.
          </p>
        )}

        {reports?.length === 0 && (
          <div className={EMPTY}>
            <FileTextIcon className="mx-auto size-8 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">
              Ei vielä raportteja. Aloita valitsemalla asiakas ja tutkimus.
            </p>
            <Button className="mt-4" onClick={() => navigate("/customers")}>
              Asiakkaat
            </Button>
          </div>
        )}

        {reports?.map((r) => (
          <button
            key={`${r.case_id}/${r.id}`}
            onClick={() => navigate(`/cases/${r.case_id}?report=${r.id}`)}
            className={ROW}
          >
            <span className="flex min-w-0 items-center gap-3">
              <FileTextIcon className="size-5 shrink-0 text-muted-foreground" />
              <span className="min-w-0">
                <span className="block truncate font-medium">{r.name}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {customerName(r.customer_id)}
                </span>
              </span>
            </span>
            <span className="ml-4 flex shrink-0 items-center gap-3">
              <span className="text-xs text-muted-foreground">{since(r.modified_at)}</span>
              <ArrowRightIcon className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
