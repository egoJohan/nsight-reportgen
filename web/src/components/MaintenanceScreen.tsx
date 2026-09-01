import { useEffect, useState, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import art503 from "@/assets/error_503.webp";
import art500 from "@/assets/error_500.webp";
import {
  lastFailedPath,
  outage,
  probeReady,
  reportReachable,
  subscribe,
  type Outage,
} from "@/lib/serviceHealth";

/** Copy per outage kind.
 *
 *  The two are told apart on purpose. A 503 means the data service is away —
 *  an upgrade, a restart — and it returns by itself, so the screen promises
 *  that and keeps checking. A 500 means something broke, which waiting will
 *  not fix; promising a recovery there would be a lie, so it asks the reader
 *  to try again and says who to tell if it persists.
 */
const COPY: Record<Outage, {
  art: string;
  title: string;
  lines: string[];
  auto: boolean;
}> = {
  maintenance: {
    art: art503,
    title: "Huoltokatko",
    lines: [
      "nSight Studio ei juuri nyt saa yhteyttä tietovarastoon. Palvelua saatetaan päivittää parhaillaan.",
      "Sivu palautuu itsestään heti kun yhteys palaa — työtäsi ei tarvitse aloittaa alusta.",
    ],
    auto: true,
  },
  error: {
    art: art500,
    title: "Odottamaton virhe",
    lines: [
      "nSight Studio kohtasi virheen, josta se ei toipunut itse.",
      "Yritä uudelleen. Jos virhe toistuu, ilmoita siitä ylläpidolle — myös alla näkyvä osoite auttaa selvittämisessä.",
    ],
    auto: false,
  },
};

/** Shown over everything while the app cannot serve what the user asked for.
 *
 *  nSight Studio keeps nothing locally — cases, reports and materials all live
 *  in the hive — so during an outage there is nothing useful behind this and
 *  every query fails. One honest screen beats a broken page under a stack of
 *  identical error toasts.
 */
export function MaintenanceScreen() {
  const kind = useSyncExternalStore(subscribe, outage, () => null);
  const qc = useQueryClient();
  const [since] = useState(() => Date.now());
  const [checking, setChecking] = useState(false);
  const [stillDown, setStillDown] = useState(false);
  const failed = lastFailedPath();

  // `?maintenance=1` / `?maintenance=error` shows a screen on demand, so it can
  // be looked at and reviewed without breaking anything to see it. Display
  // only: the polling below stays off, so a forced screen never clears itself
  // and never claims the service is unwell when it is not.
  const forcedParam =
    typeof location !== "undefined"
      ? new URLSearchParams(location.search).get("maintenance")
      : null;
  const forced: Outage | null =
    forcedParam === null ? null : forcedParam === "error" ? "error" : "maintenance";

  const shown: Outage | null = kind ?? forced;
  const copy = shown ? COPY[shown] : null;

  /** Try again now. Refetching the queries IS retrying what failed: the request
   *  that raised this screen was one of them, and re-running it alone would
   *  leave the rest of the page stale. */
  const retry = async () => {
    setChecking(true);
    setStillDown(false);
    const ok = await probeReady();
    setChecking(false);
    if (ok) {
      reportReachable();
      await qc.invalidateQueries();
    } else {
      setStillDown(true);
    }
  };

  useEffect(() => {
    if (!kind || forced || !COPY[kind].auto) return;
    let stop = false;
    const tick = async () => {
      if (stop) return;
      setChecking(true);
      const ok = await probeReady();
      setChecking(false);
      if (stop || !ok) return;
      reportReachable();
      // Everything on screen was fetched against a server that was not
      // answering; refetch rather than trusting any of it.
      qc.invalidateQueries();
    };
    void tick();  // an outage that already ended should not cost a full interval
    const id = setInterval(() => void tick(), 5000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [kind, forced, qc]);

  if (!shown || !copy) return null;

  const minutes = Math.floor((Date.now() - since) / 60000);
  return (
    <div
      role="alert"
      aria-live="assertive"
      // Opaque, not a translucent modal: the app behind is not usable and
      // showing it blurred through the message invites the reader to try. This
      // is the page now, not something on top of one.
      className="fixed inset-0 z-[100] flex items-center justify-center bg-background"
    >
      <div className="mx-4 max-w-lg space-y-4 rounded-lg border bg-card p-8 text-center shadow-lg">
        <img src={copy.art} alt="" aria-hidden="true"
             className="mx-auto w-full max-w-[320px]" />
        <h2 className="text-lg font-semibold">{copy.title}</h2>
        {copy.lines.map((line) => (
          <p key={line} className="text-sm text-muted-foreground">{line}</p>
        ))}
        {failed ? (
          <p className="break-all font-mono text-xs text-muted-foreground">{failed}</p>
        ) : null}
        <Button onClick={() => void retry()} disabled={checking} className="w-full">
          {checking ? "Yritetään…" : "Yritä uudelleen"}
        </Button>
        {forced ? (
          <p className="text-xs text-muted-foreground">
            Esikatselu (?maintenance={forcedParam}) — palvelu toimii normaalisti.
          </p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          {stillDown
            ? "Yhteyttä ei vieläkään saada."
            : copy.auto
              ? "Yritetään automaattisesti 5 s välein"
              : "Virhe ei korjaannu odottamalla."}
          {minutes >= 1 ? ` · ${minutes} min` : ""}
        </p>
      </div>
    </div>
  );
}
