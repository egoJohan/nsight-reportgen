import { useNavigate } from "react-router-dom";
import { FileTextIcon, ArrowRightIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecentReports, useCustomers } from "@/lib/queries";
import { ROW, EMPTY, ERROR } from "@/lib/surfaces";
import TiledBackdrop from "@/components/layout/TiledBackdrop";

/** Relative time at the granularity a report list actually needs. An exact
 *  timestamp is noise here — "3 pv sitten" answers "what was I last working
 *  on?", which is the only question this list is asked. */
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

/** The welcome page: brand, then what you were last working on.
 *
 *  The tiled backdrop lives HERE rather than in the shell. On a working page it
 *  competes with tables, charts and forms for attention; on the landing page it
 *  is the only decoration and has nothing to fight with. */
export default function RecentReportsPage() {
  const navigate = useNavigate();
  const { data: reports, isLoading, isError } = useRecentReports(10);
  const { data: customers } = useCustomers();

  const customerName = (id: string) =>
    customers?.find((c) => c.id === id)?.name ?? "";

  return (
    <div className="relative isolate min-h-full">
      <TiledBackdrop />

      <div className="mx-auto w-full max-w-4xl px-6 py-16">
        {/* Welcome hero */}
        <div className="flex flex-col items-center text-center">
          <div className="flex items-center justify-center rounded-2xl bg-primary px-7 py-5 shadow-sm">
            <img src="/nsight-logo.svg" alt="nSight" className="h-12 w-auto" />
          </div>
          <h1 className="mt-7 text-3xl font-semibold tracking-tight">
            Tervetuloa nSight Studioon
          </h1>
          <p className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
            Muunna SPSS-kyselydata viimeistellyiksi raporteiksi. Luo asiakas, tuo
            sille tutkimus ja rakenna raportit sen kysymyksistä.
          </p>
        </div>

        {/* Recent reports */}
        <div className="mt-16">
          <h2 className="mb-3 text-sm font-medium tracking-wide text-muted-foreground uppercase">
            Viimeisimmät raportit
          </h2>

          <div className="space-y-2">
            {isLoading &&
              [0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full rounded-lg" />)}

            {isError && <p className={ERROR}>Raporttien haku epäonnistui.</p>}

            {reports?.length === 0 && (
              <div className={EMPTY}>
                <FileTextIcon className="mx-auto size-7 text-muted-foreground/50" />
                <p className="mt-3 text-sm font-medium">Ei vielä raportteja</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Aloita luomalla asiakas ja tuomalla sille tutkimus.
                </p>
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
                  <span className="text-xs text-muted-foreground">
                    {since(r.modified_at)}
                  </span>
                  <ArrowRightIcon className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
