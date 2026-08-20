import { useRef, useState } from "react";
import {
  UploadIcon,
  Trash2Icon,
  Loader2Icon,
  AlertTriangleIcon,
  CheckIcon,
  ServerOffIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { EMPTY, PAGE, PAGE_TITLE, PANEL, PANEL_TITLE, ROW } from "@/lib/surfaces";
import {
  useFontSettings, useFontActions, useChartFont, useSetChartFont,
} from "@/lib/queries";
import type { InstalledFont, MissingFont } from "@/lib/api";

function bytes(n: number): string {
  return n > 1_000_000 ? `${(n / 1_000_000).toFixed(1)} MB` : `${Math.round(n / 1000)} kB`;
}

/** Fonts a template asks for that this host cannot supply.
 *
 *  Listed first and named individually because it is the only actionable thing
 *  on the page: nSight will not fetch commercial fonts, so somebody has to
 *  upload them, and this says which ones and whose decks are affected.
 */
function MissingFonts({ missing }: { missing: MissingFont[] }) {
  if (missing.length === 0) return null;
  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4">
      <div className="flex items-center gap-2">
        <AlertTriangleIcon className="size-4 shrink-0 text-amber-600" />
        <h3 className={PANEL_TITLE}>Missing fonts</h3>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        These fonts are missing from the server. The PowerPoint file still
        names the template's own font and looks right on a machine that has it
        installed — but the preview and the PDF use a substitute. Upload the
        font below if you hold a licence for it.
      </p>
      <ul className="mt-3 space-y-2">
        {missing.map((m) => (
          <li key={m.family} className="text-sm">
            <span className="font-medium">{m.family}</span>
            <span className="text-muted-foreground">
              {" "}
              — {m.templates.join(", ")}
            </span>
            {m.reason && (
              <p className="mt-0.5 text-xs text-muted-foreground">{m.reason}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function FontRow({ font }: { font: InstalledFont }) {
  const actions = useFontActions();
  return (
    <div className={`${ROW} gap-3`}>
      <div className="flex min-w-0 items-center gap-2">
        {font.on_host ? (
          <CheckIcon className="size-4 shrink-0 text-primary" />
        ) : (
          // Stored in datahive but not on this machine — what a restarted or
          // replaced render host looks like before the startup sync runs.
          <ServerOffIcon className="size-4 shrink-0 text-amber-600" />
        )}
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{font.family}</p>
          <p className="truncate text-xs text-muted-foreground">
            {font.filename} · {bytes(font.size)}
            {!font.on_host && " · not on this server"}
          </p>
        </div>
      </div>
      <Button
        size="icon-sm"
        variant="ghost"
        title="Remove font"
        disabled={actions.remove.isPending}
        onClick={() =>
          actions.remove.mutate(font.id, {
            onSuccess: () => toast.success(`Font '${font.family}' removed`),
            onError: (e) => toast.error(e.message),
          })
        }
      >
        <Trash2Icon className="size-4" />
      </Button>
    </div>
  );
}

/** The font chart text is drawn in — deliberately not the template's.
 *
 *  A brand display face is usually designed for headlines, and chart text is
 *  mostly long category labels. Picking a narrower face fits more of a label
 *  before it truncates or rotates, so this is a separate choice rather than
 *  something inherited from the pohja.
 */
function ChartFontSetting() {
  const { data } = useChartFont();
  const set = useSetChartFont();

  if (!data) return null;
  const fellBack = data.family !== "" && data.effective !== data.family;

  return (
    <div className={`${PANEL} p-4`}>
      <h3 className={PANEL_TITLE}>Chart font</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        Chart text is drawn in this font. It is deliberately separate from the
        template's own: a narrower face fits more of a long answer option before
        it is truncated.
      </p>

      <div className="mt-3 flex items-center gap-2">
        <select
          className="h-8 min-w-0 flex-1 rounded-lg border border-input bg-surface px-2.5 text-sm"
          value={data.family}
          disabled={set.isPending}
          onChange={(e) =>
            set.mutate(e.target.value, {
              onError: (err) => toast.error(err.message),
            })
          }
        >
          <option value="">Default ({data.default})</option>
          {data.available.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        {set.isPending && (
          <Loader2Icon className="size-4 animate-spin text-muted-foreground" />
        )}
      </div>

      {fellBack && (
        <p className="mt-2 text-xs text-amber-600">
          The chosen font was not found, so {data.effective} is in use.
        </p>
      )}
    </div>
  );
}

function FontsTab() {
  const { data, isLoading } = useFontSettings();
  const actions = useFontActions();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function upload(file: File) {
    actions.upload.mutate(file, {
      onSuccess: (f) => toast.success(`Font '${f.family}' installed`),
      // The reason is the point — "this is a WOFF, not a .ttf" is what stops
      // someone retrying the same file. Long duration so it can be read.
      onError: (e) => toast.error(e.message, { duration: 12000 }),
    });
  }

  return (
    <div className="space-y-6">
      {data && <MissingFonts missing={data.missing} />}

      <ChartFontSetting />

      <div className={`${PANEL} p-4`}>
        <h3 className={PANEL_TITLE}>Installed fonts</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          nSight installs open-licence fonts from Google Fonts by itself. It
          does not fetch commercial ones (Century Gothic, Calibri, Verdana and
          the like), because the licence is not nSight's to use. Upload those
          here — you are responsible for holding the right to the font.
        </p>

        <div
          className={`mt-4 flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-8 text-center transition-colors ${
            dragging ? "border-primary bg-primary/5" : "border-border"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files?.[0];
            if (f) upload(f);
          }}
        >
          {actions.upload.isPending ? (
            <Loader2Icon className="size-5 animate-spin text-muted-foreground" />
          ) : (
            <UploadIcon className="size-5 text-muted-foreground" />
          )}
          <p className="mt-2 text-sm">
            {actions.upload.isPending
              ? "Installing…"
              : "Drop a .ttf or .otf font here"}
          </p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            disabled={actions.upload.isPending}
            onClick={() => fileRef.current?.click()}
          >Choose a file</Button>
          <input
            ref={fileRef}
            type="file"
            accept=".ttf,.otf,font/ttf,font/otf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload(f);
              e.target.value = "";
            }}
          />
        </div>

        <div className="mt-4 space-y-1">
          {isLoading && (
            <p className="text-xs text-muted-foreground">Loading…</p>
          )}
          {data?.fonts.length === 0 && !isLoading && (
            <p className={`${EMPTY} text-sm text-muted-foreground`}>
              No hand-installed fonts. The system's own fonts are in use
              without being installed here.
            </p>
          )}
          {data?.fonts.map((f) => (
            <FontRow key={f.id} font={f} />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <div className={PAGE}>
      <h1 className={PAGE_TITLE}>Settings</h1>

      <Tabs defaultValue="fonts" className="mt-6">
        <TabsList>
          <TabsTrigger value="fonts">Fonts</TabsTrigger>
        </TabsList>
        <TabsContent value="fonts" className="mt-4">
          <FontsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
