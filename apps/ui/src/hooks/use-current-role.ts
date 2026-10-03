// Best-effort resolution of the signed-in member's role (read < write <
// admin) by matching the Clerk email against the members roster (read-floor,
// so any principal can list it).
//
// This is a UX affordance only — the server enforces role floors regardless.
// When the role can't be resolved (roster fetch fails, email not found) we
// return null, and the UI should show controls and surface any 403 cleanly
// (`useHasRole`) — except for an affordance a member does not need, which is
// offered only to a role KNOWN to meet its floor (`roleIsKnownToMeet`).

import { useQuery } from "@tanstack/react-query";

import { tenantApi } from "@/api/client";
import { unwrap } from "@/api/problem";
import { API_PROVIDER, mockDelay } from "@/lib/api-provider";
import { roleRank } from "@/lib/labels";

import { useAuthUser } from "./use-auth";

/** The three role floors, lowest first. */
export type RoleFloor = "read" | "write" | "admin";

/**
 * The signed-in member's role when there is no server — the one source mock
 * mode has for it, read both by this hook and by any feature mock that
 * enforces a floor the way the server does (the Code Builder's draft preview,
 * #579), so the two answer from the same value. The hook's answer is cached
 * like a real one, so a change here reaches the page only when it asks again —
 * which is how a page can come to believe a role the server no longer grants.
 * An admin unless a test or a developer says otherwise.
 */
let mockMemberRole: string | null = "admin";

/** Mock mode only: who the signed-in developer is. `null` is a role nobody resolved. */
export function setMockMemberRole(role: string | null): void {
  mockMemberRole = role;
}

/** Mock mode only: the role `setMockMemberRole` last set. */
export function currentMockMemberRole(): string | null {
  return mockMemberRole;
}

async function fetchRoleByEmail(email: string): Promise<string | null> {
  if (API_PROVIDER === "mock") {
    await mockDelay(100);
    return mockMemberRole;
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
export function useHasRole(floor: RoleFloor): boolean {
  const { role } = useCurrentRole();
  if (role === null) return true;
  return roleRank(role) >= roleRank(floor);
}

/**
 * True only when the role is RESOLVED and meets the floor — the opposite
 * default to `useHasRole`, for an affordance a member does not need and the
 * server refuses below its floor. Offering it to someone it would refuse buys
 * a guaranteed `403`; hiding it from an admin whose role could not be resolved
 * costs them an option, not their work. Pure, so a page can hand it the role
 * `useCurrentRole` returned.
 */
export function roleIsKnownToMeet(
  role: string | null,
  floor: RoleFloor,
): boolean {
  return role !== null && roleRank(role) >= roleRank(floor);
}
