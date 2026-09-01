import { Link, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import art404 from "@/assets/error_404.webp";

/** An address that leads nowhere.
 *
 *  Without this an unknown URL rendered a blank page inside the shell — the
 *  navigation was there, the content area simply stayed empty, which reads as a
 *  fault in the app rather than a wrong address. A typed link, a stale
 *  bookmark and a report someone else deleted all arrive here.
 */
export default function NotFoundPage() {
  const { pathname } = useLocation();
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-8">
      <div className="max-w-lg space-y-4 text-center">
        <img src={art404} alt="" aria-hidden="true"
             className="mx-auto w-full max-w-[320px]" />
        <h1 className="text-lg font-semibold">Sivua ei löytynyt</h1>
        <p className="text-sm text-muted-foreground">
          nSight Studio ei tunne tätä osoitetta. Linkki voi olla vanhentunut, tai
          kohde on poistettu.
        </p>
        <p className="break-all font-mono text-xs text-muted-foreground">
          {pathname}
        </p>
        <Button asChild>
          <Link to="/">Takaisin etusivulle</Link>
        </Button>
      </div>
    </div>
  );
}
