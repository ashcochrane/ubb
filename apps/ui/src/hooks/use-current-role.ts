// Best-effort resolution of the signed-in member's role (read < write <
// admin) by matching the Clerk email against the members roster (read-floor,
// so any principal can list it).
//
// This is a UX affordance only — the server enforces role floors regardless.
// When the role can't be resolved (roster fetch fails, email not found) we
// return null and the UI should show controls and surface any 403 cleanly.

import { useQuery } from "@tanstack/react-query";

import { tenantApi } from "@/api/client";
import { unwrap } from "@/api/problem";
import { API_PROVIDER, mockDelay } from "@/lib/api-provider";
import { roleRank } from "@/lib/labels";

import { useAuthUser } from "./use-auth";

async function fetchRoleByEmail(email: string): Promise<string | null> {
  if (API_PROVIDER === "mock") {
    await mockDelay(100);
    return "admin";
  }
  let cursor: string | undefined;
  // The roster is small; walk at most a handful of pages defensively.
  for (let page = 0; page < 10; page++) {
    const result = unwrap(
      await tenantApi.GET("/members", {
        params: { query: { cursor, limit: 100 } },
      }),
    );
    const match = result.data.find(
      (member) => member.email.toLowerCase() === email.toLowerCase(),
    );
    if (match) return match.role;
    if (!result.has_more || !result.next_cursor) return null;
    cursor = result.next_cursor;
  }
  return null;
}

export function useCurrentRole(): {
  role: string | null;
  /** True once resolution finished (successfully or not). */
  resolved: boolean;
} {
  const { email } = useAuthUser();
  const query = useQuery({
    queryKey: ["tenant", "current-role", email] as const,
    queryFn: () => fetchRoleByEmail(email),
    enabled: email !== "",
    staleTime: 5 * 60_000,
    retry: 0,
    throwOnError: false,
  });
  return { role: query.data ?? null, resolved: !query.isLoading };
}

/**
 * True when the member's role meets the floor — or when the role is unknown
 * (fail open in the UI; the server still enforces).
 */
export function useHasRole(floor: "read" | "write" | "admin"): boolean {
  const { role } = useCurrentRole();
  if (role === null) return true;
  return roleRank(role) >= roleRank(floor);
}
