import { useRef, useState } from "react";
import {
  UploadIcon,
  Trash2Icon,
  Loader2Icon,
  AlertTriangleIcon,
  CheckIcon,
  ServerOffIcon,
  MailIcon,
  CopyIcon,
  PlusIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { EMPTY, PAGE, PAGE_TITLE, PANEL, PANEL_TITLE, ROW, SECTION_HEADER } from "@/lib/surfaces";
import {
  useFontSettings, useFontActions, useChartFont, useSetChartFont,
  useUsers, useInvites, useUserActions, useCustomers,
} from "@/lib/queries";
import { useSession } from "@/lib/session";
import type { InstalledFont, MissingFont, StudioUser, Invite, UserGrantInput } from "@/lib/api";

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

/** Adds one customer grant to the set being built, at "view" or "edit". Used
 *  inside the invite dialog — a colleague should not land in an empty app,
 *  so an invite can hand them access up front instead of a second trip here
 *  once they've signed in. */
function GrantPicker({
  grants,
  onChange,
}: {
  grants: UserGrantInput[];
  onChange: (grants: UserGrantInput[]) => void;
}) {
  const { data: customers } = useCustomers();
  const [customerId, setCustomerId] = useState("");
  const [mode, setMode] = useState<"view" | "edit">("view");

  function add() {
    if (!customerId || grants.some((g) => g.scope === customerId)) return;
    onChange([...grants, { scope: customerId, mode }]);
    setCustomerId("");
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <select
          className="h-8 min-w-0 flex-1 rounded-lg border border-input bg-surface px-2.5 text-sm"
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value)}
        >
          <option value="">Choose a customer…</option>
          {(customers ?? [])
            .filter((c) => !grants.some((g) => g.scope === c.id))
            .map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
        </select>
        <select
          className="h-8 w-24 rounded-lg border border-input bg-surface px-2.5 text-sm"
          value={mode}
          onChange={(e) => setMode(e.target.value as "view" | "edit")}
        >
          <option value="view">View</option>
          <option value="edit">Edit</option>
        </select>
        <Button size="sm" variant="outline" disabled={!customerId} onClick={add}>
          <PlusIcon className="size-4" />
        </Button>
      </div>
      {grants.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {grants.map((g) => {
            const name = (customers ?? []).find((c) => c.id === g.scope)?.name ?? g.scope;
            return (
              <Badge key={g.scope} variant="secondary" className="gap-1">
                {name} · {g.mode}
                <button
                  type="button"
                  className="ml-1 opacity-60 hover:opacity-100"
                  onClick={() => onChange(grants.filter((x) => x.scope !== g.scope))}
                >
                  ×
                </button>
              </Badge>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Invite by email, optionally handing over customer access up front.
 *
 *  The token is returned exactly once, in this response — there is no way
 *  to fetch it again once the dialog closes, so it stays on screen with a
 *  copy button until the admin dismisses it. `emailed: false` is the normal
 *  case on a machine with no SMTP configured; the dialog does not pretend an
 *  email is on its way when it is not.
 */
function InviteDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const actions = useUserActions();
  const [email, setEmail] = useState("");
  const [grants, setGrants] = useState<UserGrantInput[]>([]);
  const [result, setResult] = useState<{ link: string; emailed: boolean } | null>(null);

  function reset() {
    setEmail("");
    setGrants([]);
    setResult(null);
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite someone to nSight Studio</DialogTitle>
          <DialogDescription>
            They&rsquo;ll get an email with a link to sign in. Access is granted the moment they accept.
          </DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="space-y-3 text-sm">
            {result.emailed ? (
              <p className="flex items-center gap-2 text-primary">
                <MailIcon className="size-4" /> Invitation sent.
              </p>
            ) : (
              <p className="text-amber-600">
                Email could not be sent — copy the link below and share it yourself.
              </p>
            )}
            <div className="flex items-center gap-2 rounded-lg border bg-surface p-2">
              <code className="min-w-0 flex-1 truncate text-xs">{result.link}</code>
              <Button
                size="icon-sm"
                variant="ghost"
                title="Copy link"
                onClick={() => {
                  navigator.clipboard.writeText(result.link);
                  toast.success("Link copied");
                }}
              >
                <CopyIcon className="size-4" />
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <Input
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
            />
            <GrantPicker grants={grants} onChange={setGrants} />
          </div>
        )}
        <DialogFooter>
          {result ? (
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          ) : (
            <Button
              disabled={!email || actions.invite.isPending}
              onClick={() =>
                actions.invite.mutate(
                  { email, grants },
                  {
                    onSuccess: (r) => setResult({ link: r.link, emailed: r.emailed }),
                    onError: (e) => toast.error(e.message),
                  }
                )
              }
            >
              Send invite
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** One user, their admin flag, and their customer grants — the grants are
 *  removed individually here (an × on the badge); changing a grant's mode
 *  reuses the same picker, added at the bottom of the row. */
function UserRow({ user, isSelf }: { user: StudioUser; isSelf: boolean }) {
  const actions = useUserActions();
  const [editingGrants, setEditingGrants] = useState(false);

  function setMode(scope: string, mode: "view" | "edit") {
    actions.setGrants.mutate({
      userId: user.id,
      grants: user.grants.map((g) => (g.scope === scope ? { scope, mode } : { scope: g.scope, mode: g.mode })),
    }, { onError: (e) => toast.error(e.message) });
  }

  function removeGrant(scope: string) {
    actions.setGrants.mutate({
      userId: user.id,
      grants: user.grants.filter((x) => x.scope !== scope).map((x) => ({ scope: x.scope, mode: x.mode })),
    }, { onError: (e) => toast.error(e.message) });
  }

  function addGrants(added: UserGrantInput[]) {
    const merged = [
      ...user.grants.map((g) => ({ scope: g.scope, mode: g.mode })),
      ...added.filter((a) => !user.grants.some((g) => g.scope === a.scope)),
    ];
    actions.setGrants.mutate({ userId: user.id, grants: merged }, { onError: (e) => toast.error(e.message) });
  }

  return (
    <div className={`${ROW} flex-col items-stretch gap-3`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{user.email}</p>
          {user.grants.length === 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">No customers granted yet</p>
          ) : (
            <div className="mt-1 flex flex-wrap gap-1">
              {user.grants.map((g) => (
                <Badge key={g.scope} variant={g.customer_name ? "secondary" : "destructive"} className="gap-1">
                  {g.customer_name ?? "deleted"}
                  {g.case_name ? ` / ${g.case_name}` : ""} ·{" "}
                  <button
                    type="button"
                    className="underline decoration-dotted underline-offset-2"
                    title="Switch between view and edit"
                    onClick={() => setMode(g.scope, g.mode === "view" ? "edit" : "view")}
                  >
                    {g.mode}
                  </button>
                  <button
                    type="button"
                    className="ml-1 opacity-60 hover:opacity-100"
                    title="Remove this grant"
                    onClick={() => removeGrant(g.scope)}
                  >
                    ×
                  </button>
                </Badge>
              ))}
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            Admin
            <Switch
              size="sm"
              checked={user.is_admin}
              disabled={actions.setAdmin.isPending}
              onCheckedChange={(checked) =>
                actions.setAdmin.mutate(
                  { userId: user.id, isAdmin: checked },
                  { onError: (e) => toast.error(e.message) }
                )
              }
            />
          </div>
          <Button
            size="icon-sm"
            variant="ghost"
            disabled={actions.remove.isPending || isSelf}
            title={isSelf ? "You cannot remove yourself" : "Remove user"}
            onClick={() =>
              actions.remove.mutate(user.id, {
                onSuccess: () => toast.success(`${user.email} removed`),
                onError: (e) => toast.error(e.message),
              })
            }
          >
            <Trash2Icon className="size-4" />
          </Button>
        </div>
      </div>
      {editingGrants ? (
        <GrantPicker grants={[]} onChange={(added) => { addGrants(added); setEditingGrants(false); }} />
      ) : (
        <Button size="sm" variant="outline" className="w-fit" onClick={() => setEditingGrants(true)}>
          <PlusIcon className="size-4" /> Grant a customer
        </Button>
      )}
    </div>
  );
}

/** A pending, accepted or expired invitation. Revoking a pending one simply
 *  withdraws it; revoking an already-accepted one removes the user it made —
 *  the button's title says which is about to happen. */
function InviteRow({ invite }: { invite: Invite }) {
  const actions = useUserActions();
  return (
    <div className={`${ROW} gap-3`}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{invite.email}</p>
        <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
          Invited {new Date(invite.invited_at).toLocaleDateString()}
          <Badge
            variant={
              invite.status === "pending" ? "secondary" : invite.status === "accepted" ? "outline" : "destructive"
            }
          >
            {invite.status}
          </Badge>
        </p>
      </div>
      <Button
        size="icon-sm"
        variant="ghost"
        disabled={actions.revokeInvite.isPending}
        title={invite.status === "accepted" ? "Revoke and remove this user" : "Revoke invitation"}
        onClick={() =>
          actions.revokeInvite.mutate(invite.id, {
            onError: (e) => toast.error(e.message),
          })
        }
      >
        <Trash2Icon className="size-4" />
      </Button>
    </div>
  );
}

/** Users, then pending/past invitations. The grant editor on each user row is
 *  the point of this whole screen: a colleague who signs in with no grants
 *  lands in an empty app, so this is where that gets fixed. */
function UsersTab() {
  const { data: me } = useSession();
  const { data: users, isLoading } = useUsers();
  const { data: invites } = useInvites();
  const [inviting, setInviting] = useState(false);

  return (
    <div className="space-y-6">
      <div className={SECTION_HEADER}>
        <h3 className={PANEL_TITLE}>Users</h3>
        <Button size="sm" variant="outline" onClick={() => setInviting(true)}>
          <PlusIcon className="size-4" /> Invite
        </Button>
      </div>
      <div className="space-y-2">
        {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}
        {users?.length === 0 && !isLoading && (
          <p className={`${EMPTY} text-sm text-muted-foreground`}>No users yet.</p>
        )}
        {users?.map((u) => <UserRow key={u.id} user={u} isSelf={u.id === me?.id} />)}
      </div>

      {invites && invites.length > 0 && (
        <div>
          <h3 className={PANEL_TITLE}>Invitations</h3>
          <div className="mt-2 space-y-2">
            {invites.map((i) => <InviteRow key={i.id} invite={i} />)}
          </div>
        </div>
      )}

      <InviteDialog open={inviting} onOpenChange={setInviting} />
    </div>
  );
}

export default function SettingsPage() {
  const { data: me } = useSession();

  return (
    <div className={PAGE}>
      <h1 className={PAGE_TITLE}>Settings</h1>

      <Tabs defaultValue="fonts" className="mt-6">
        <TabsList>
          <TabsTrigger value="fonts">Fonts</TabsTrigger>
          {me?.is_admin && <TabsTrigger value="users">Users</TabsTrigger>}
        </TabsList>
        <TabsContent value="fonts" className="mt-4">
          <FontsTab />
        </TabsContent>
        {me?.is_admin && (
          <TabsContent value="users" className="mt-4">
            <UsersTab />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
