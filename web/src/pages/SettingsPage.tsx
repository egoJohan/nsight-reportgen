import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  UploadIcon,
  Trash2Icon,
  Loader2Icon,
  AlertTriangleIcon,
  CheckIcon,
  XIcon,
  ServerOffIcon,
  MailIcon,
  CopyIcon,
  PlusIcon,
  UserIcon,
  UserPlusIcon,
  UsersIcon,
  ShieldCheckIcon,
  TypeIcon,
  DatabaseIcon,
  PresentationIcon,
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
import { EMPTY, PAGE, PAGE_TITLE, PANEL_PADDED, PANEL_TITLE, ROW, SECTION_HEADER } from "@/lib/surfaces";
import {
  useFontSettings, useFontActions, useChartFont, useSetChartFont,
  useUsers, useUserActions,
  useAccessRequests, useAccessRequestActions,
} from "@/lib/queries";
import { useSession } from "@/lib/session";
import BackupTab from "@/components/settings/BackupTab";
import DefaultTemplateTab from "@/components/settings/DefaultTemplateTab";
import PendingUsersTab from "@/components/settings/PendingUsersTab";
import ProfileTab from "@/components/settings/ProfileTab";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatReportDate } from "@/lib/utils";
import type { InstalledFont, MissingFont, StudioUser, AccessRequest } from "@/lib/api";

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
    <div className={PANEL_PADDED}>
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

      <div className={PANEL_PADDED}>
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
  const [result, setResult] = useState<{ link: string; emailed: boolean } | null>(null);

  function reset() {
    setEmail("");
    setResult(null);
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite someone to nSight Studio</DialogTitle>
          <DialogDescription>
            They&rsquo;ll get an email with a link to sign in.
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
                  { email, grants: [] },
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





  return (
    <div className={`${ROW} flex-col items-stretch gap-3`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{user.email}</p>
          {/* "Never" is not a gap in the data — it is somebody who has been
              invited and has not turned up yet, which is exactly what the
              separate Invitations list used to say. */}
          <p className="mt-0.5 text-xs text-muted-foreground">
            {user.last_login_at
              ? `Last signed in ${formatReportDate(user.last_login_at)}`
              : "Never signed in"}
          </p>
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
    </div>
  );
}

/** A pending, accepted or expired invitation. Revoking a pending one simply
 *  withdraws it; revoking an already-accepted one removes the user it made —
 *  the button's title says which is about to happen. */
/** One PENDING permission request -- who asked, for which customer, at what
 *  mode, and when. The queue this feeds (`useAccessRequests`) is already
 *  filtered server-side to "pending", so approve/refuse are always live
 *  here -- there is no decided state left to render specially, and once one
 *  is decided it drops out of the list rather than lingering with a badge. */
function AccessRequestRow({ request }: { request: AccessRequest }) {
  const actions = useAccessRequestActions();
  return (
    <div className={`${ROW} gap-3`}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">
          {request.user_email}
          <span className="font-normal text-muted-foreground">
            {" "}
            wants {request.mode} access to {request.customer_name ?? "a removed customer"}
          </span>
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Requested {new Date(request.requested_at).toLocaleDateString()}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button
          size="icon-sm"
          variant="ghost"
          disabled={actions.refuse.isPending || actions.approve.isPending}
          title="Refuse"
          onClick={() =>
            actions.refuse.mutate(request.id, { onError: (e) => toast.error(e.message) })
          }
        >
          <XIcon className="size-4" />
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          disabled={actions.refuse.isPending || actions.approve.isPending}
          title="Approve"
          onClick={() =>
            actions.approve.mutate(request.id, {
              onSuccess: () => toast.success(`Granted ${request.mode} access to ${request.user_email}`),
              onError: (e) => toast.error(e.message),
            })
          }
        >
          <CheckIcon className="size-4" />
        </Button>
      </div>
    </div>
  );
}

/** Its own tab (see SettingsPage below) rather than a section buried inside
 *  Users -- an admin who lands on Fonts by default should still see the
 *  queue is there, and a pending count on the tab itself is what makes that
 *  true without clicking in. Reads as empty most of the time on purpose:
 *  a decided request drops out of the list (`useAccessRequests` only ever
 *  returns "pending"), so "No permission requests right now" is the normal
 *  state of a well-run queue, not a placeholder waiting to be replaced. */
function PermissionRequestsTab() {
  const { data: requests, isLoading } = useAccessRequests();
  return (
    <div className="space-y-2">
      {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}
      {requests?.length === 0 && !isLoading && (
        <p className={`${EMPTY} text-sm text-muted-foreground`}>
          No permission requests right now.
        </p>
      )}
      {requests?.map((r) => <AccessRequestRow key={r.id} request={r} />)}
    </div>
  );
}

/** Users, then pending/past invitations. The grant editor on each user row is
 *  the point of this whole screen: a colleague who signs in with no grants
 *  lands in an empty app, so this is where that gets fixed. */
function UsersTab() {
  const { data: me } = useSession();
  const { data: users, isLoading } = useUsers();
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

      <InviteDialog open={inviting} onOpenChange={setInviting} />
    </div>
  );
}

export default function SettingsPage() {
  const { data: me } = useSession();
  // Admin, or a customer's owner (edit on at least one -- see
  // permissions.py): the same rule `list_access_requests` enforces
  // server-side. `is_owner` comes off /auth/me rather than being worked out
  // here from every grant, which the session response never carries (spec
  // §5's "no grants over the wire beyond what's needed").
  const canSeePermissionRequests = !!me && (me.is_admin || me.is_owner);
  // Lifted above the tab so the pending count shows on the tab ITSELF, not
  // only once someone has already clicked into it. Disabled entirely for
  // someone who cannot see the tab at all, rather than firing a request
  // whose result (always []) would just be discarded.
  const { data: permissionRequests } = useAccessRequests(canSeePermissionRequests);
  const pendingCount = permissionRequests?.length ?? 0;
  // Same reason as above: the count belongs on the tab, so somebody waiting to
  // be let in is visible without a click. Admin-only, so not fetched for
  // anyone who cannot act on it.
  const { data: pendingUsers } = useQuery({
    queryKey: ["signup-requests"],
    queryFn: api.signup.pending,
    enabled: !!me?.is_admin,
  });
  const pendingUserCount = pendingUsers?.length ?? 0;

  // People first, fonts are set once and forgotten: Users, then Permission
  // requests, then Fonts. Users and Permission requests are each gated;
  // Fonts stays open to anyone signed in, so there is always at least one
  // tab to land on -- the fallback just has to be the FIRST of the three
  // this particular caller actually has, or an admin-only tab could be
  // handed to someone who can't see it. That needs `me` resolved first
  // (is_admin/is_owner are both on it), so the strip waits for it rather
  // than guessing and re-defaulting once it arrives.
  const [searchParams] = useSearchParams();
  // A plain user lands on their own tab, not on Fonts — it is first in the
  // strip and it is the one thing here that belongs to them.
  const fallbackTab = !me ? undefined : me.is_admin ? "users" : canSeePermissionRequests ? "permission-requests" : "profile";
  // ?tab=permission-requests is the landing spot the access-request email
  // links to (routes_access_requests.py's create_access_request) -- honour
  // it ONLY when this caller can actually see that tab, so a stale or
  // tampered link falls back to the same default anyone else gets rather
  // than silently no-oping on a tab that was never rendered.
  const requestedTab = searchParams.get("tab");
  const visible = new Set(
    [me && "profile", me?.is_admin && "users", me?.is_admin && "pending-users",
     canSeePermissionRequests && "permission-requests",
     me && "fonts", me?.is_admin && "default-template",
     me?.is_admin && "backup"].filter(Boolean)
  );
  const defaultTab = requestedTab && visible.has(requestedTab) ? requestedTab : fallbackTab;

  return (
    <div className={PAGE}>
      <h1 className={PAGE_TITLE}>Settings</h1>

      {me && (
        <Tabs defaultValue={defaultTab} className="mt-6">
          <TabsList>
            {/* First, and open to everyone: the only tab here that is about
                you rather than about administering something. */}
            <TabsTrigger value="profile">
              <UserIcon className="size-4" />Personal information
            </TabsTrigger>
            {me.is_admin && (
              <TabsTrigger value="users">
                <UsersIcon className="size-4" />Users
              </TabsTrigger>
            )}
            {/* Right after Users: both are "who is in this hive", and a
                person waiting to get in is the more urgent of the two. */}
            {me.is_admin && (
              <TabsTrigger value="pending-users">
                <UserPlusIcon className="size-4" />Pending users
                {pendingUserCount > 0 && (
                  <Badge variant="secondary" className="font-normal">{pendingUserCount}</Badge>
                )}
              </TabsTrigger>
            )}
            {canSeePermissionRequests && (
              <TabsTrigger value="permission-requests">
                <ShieldCheckIcon className="size-4" />Permission requests
                {pendingCount > 0 && (
                  <Badge variant="secondary" className="font-normal">{pendingCount}</Badge>
                )}
              </TabsTrigger>
            )}
            {/* Unchanged: open to anyone signed in, not just an admin --
                fonts are a server-wide resource, not customer access. */}
            <TabsTrigger value="fonts">
              <TypeIcon className="size-4" />Fonts
            </TabsTrigger>
            {/* Admin-only: one upload restyles every report that has no
                template of its own, which is the whole point of it. */}
            {me.is_admin && (
              <TabsTrigger value="default-template">
                <PresentationIcon className="size-4" />Default template
              </TabsTrigger>
            )}
            {/* Last: taking a backup is a thing you do rarely and
                deliberately, not a screen to land on. Admin-only — the
                archive carries every password hash and the signing key. */}
            {me.is_admin && (
              <TabsTrigger value="backup">
                <DatabaseIcon className="size-4" />Backup
              </TabsTrigger>
            )}
          </TabsList>
          <TabsContent value="profile" className="mt-4">
            <ProfileTab />
          </TabsContent>
          {me.is_admin && (
            <TabsContent value="pending-users" className="mt-4">
              <PendingUsersTab />
            </TabsContent>
          )}
          {me.is_admin && (
            <TabsContent value="users" className="mt-4">
              <UsersTab />
            </TabsContent>
          )}
          {canSeePermissionRequests && (
            <TabsContent value="permission-requests" className="mt-4">
              <PermissionRequestsTab />
            </TabsContent>
          )}
          <TabsContent value="fonts" className="mt-4">
            <FontsTab />
          </TabsContent>
          {me.is_admin && (
            <TabsContent value="default-template" className="mt-4">
              <DefaultTemplateTab />
            </TabsContent>
          )}
          {me.is_admin && (
            <TabsContent value="backup" className="mt-4">
              <BackupTab />
            </TabsContent>
          )}
        </Tabs>
      )}
    </div>
  );
}
