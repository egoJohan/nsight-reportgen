// Whether anyone is signed in can only be answered by asking the server: the
// session cookie is HttpOnly (deliberately — JS reading it would be a target
// for the exact class of attack the cookie exists to prevent), so there is no
// client-side flag to check first. `/auth/me` IS the check.
import { useQuery } from "@tanstack/react-query";
import { clearLegacyWorkspaceStorage } from "./workspace";

export interface Me {
  id: string;
  email: string;
  name: string;
  is_admin: boolean;
}

// Relative by default (spec §5.4), matching api.ts: same-origin is what makes
// the SameSite=Strict session cookie work at all, in prod (nginx) and in dev
// (the Vite proxy) alike.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

/** null = not signed in (401); undefined while loading; a Me once resolved.
 *
 *  `retry: false` matters here specifically: react-query's default retry
 *  would turn one 401 into several while AppShell is deciding whether to
 *  redirect, each one a real request against the backend.
 */
export function useSession() {
  return useQuery<Me | null>({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/auth/me`);
      if (res.status === 401) return null;
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.json();
    },
    retry: false,
    staleTime: 60_000,
  });
}

export async function signOut(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, { method: "POST" });
  // Per-case state now lives server-side and dies with the in-memory
  // react-query cache on the hard navigation that follows sign-out. The one
  // thing that can outlive that is a pre-§8 localStorage leftover (see
  // workspace.ts) -- sweep it so a colleague signing in on this machine next
  // never inherits it.
  clearLegacyWorkspaceStorage();
}
