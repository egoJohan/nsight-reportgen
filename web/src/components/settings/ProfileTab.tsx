/**
 * Your own name.
 *
 * An account starts named after the local part of its email — better than a
 * blank space, and true from the moment it exists — so this screen is a
 * correction, not a form somebody has to fill in before the app works.
 *
 * The only settings tab that is not about administering something. It is open
 * to everyone, because everyone has a name, and it writes through a route that
 * takes no user id at all: the server saves whoever is signed in, so there is
 * no shape of request here that renames a colleague.
 */
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { PANEL_TITLE } from "@/lib/surfaces";

export default function ProfileTab() {
  const { data: me } = useSession();
  const qc = useQueryClient();
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [loaded, setLoaded] = useState(false);

  // Seeded once. Re-seeding on every render of `me` would fight the cursor
  // after a save, when the refreshed session arrives mid-edit.
  useEffect(() => {
    if (!me || loaded) return;
    setFirst(me.first_name ?? "");
    setLast(me.last_name ?? "");
    setLoaded(true);
  }, [me, loaded]);

  const save = useMutation({
    mutationFn: () => api.profile.update(first.trim(), last.trim()),
    onSuccess: (updated) => {
      // Seed rather than invalidate: the header reads this same cache entry,
      // so the new name appears immediately instead of on the next refetch.
      qc.setQueryData(["auth", "me"], updated);
      toast.success("Saved.");
    },
    onError: (e) =>
      toast.error(e instanceof Error ? e.message : "Could not save your name"),
  });

  if (!me) return null;

  const dirty =
    first.trim() !== (me.first_name ?? "") || last.trim() !== (me.last_name ?? "");

  return (
    <div className="max-w-md space-y-4">
      <div>
        <h3 className={PANEL_TITLE}>Personal information</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          How your name appears in nSight Studio.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="first-name">First name</Label>
        <Input
          id="first-name"
          value={first}
          autoComplete="given-name"
          maxLength={100}
          onChange={(e) => setFirst(e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="last-name">Last name</Label>
        <Input
          id="last-name"
          value={last}
          autoComplete="family-name"
          maxLength={100}
          onChange={(e) => setLast(e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="profile-email">Email</Label>
        {/* Shown, never editable: it is the identity Google or Microsoft
            vouches for, and the thing every grant is attached to. Changing it
            here would be changing who you are. */}
        <Input id="profile-email" value={me.email} disabled readOnly />
        <p className="text-xs text-muted-foreground">
          You sign in with this address, so it can&rsquo;t be changed here.
        </p>
      </div>

      <Button disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? "Saving…" : "Save"}
      </Button>
    </div>
  );
}
