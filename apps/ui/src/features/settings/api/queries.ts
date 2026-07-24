// TanStack Query hooks over the provider. ALL query keys + invalidation for
// the settings feature live here. First key segment = backend namespace:
// ['tenant', …], ['connect', …], ['audit', …].

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCursorList } from "@/api/pagination";

import { settingsApi } from "./provider";
import type { AuditFilters, TenantConfig, TenantConfigPatch } from "./types";

const CONFIG_KEY = ["tenant", "config"] as const;

// --- Workspace config -------------------------------------------------------

/** Same key as the app-level bootstrap hook — one cache entry, one truth. */
export function useSettingsTenantConfig() {
  return useQuery({
    queryKey: CONFIG_KEY,
    queryFn: () => settingsApi.getTenantConfig(),
    staleTime: 5 * 60_000,
  });
}

/**
 * PATCH /tenant/config. The response is the full updated config, so it is
 * written straight into the cache before the ['tenant'] prefix invalidation
 * (over-invalidate rather than miss — config gates the whole console).
 */
export function useUpdateTenantConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: TenantConfigPatch) => settingsApi.updateTenantConfig(patch),
    onSuccess: (updated: TenantConfig) => {
      queryClient.setQueryData(CONFIG_KEY, updated);
      void queryClient.invalidateQueries({ queryKey: ["tenant"] });
    },
  });
}

// --- Stripe Connect ---------------------------------------------------------

export function useConnectStatus(options?: { poll?: boolean; enabled?: boolean }) {
  return useQuery({
    queryKey: ["connect", "status"] as const,
    queryFn: () => settingsApi.getConnectStatus(),
    enabled: options?.enabled,
    // The GET lazily re-polls Stripe server-side, so client polling after the
    // OAuth return is safe and intended. Polling stops once onboarded.
    refetchInterval: options?.poll
      ? (query) => (query.state.data?.onboarded ? false : 5_000)
      : false,
  });
}

export function useStartConnect() {
  return useMutation({
    mutationFn: (returnUrl: string) => settingsApi.startConnect(returnUrl),
  });
}

// --- Team -------------------------------------------------------------------

export function useMembers() {
  return useCursorList(["tenant", "members"], (cursor) =>
    settingsApi.listMembers(cursor),
  );
}

export function useUpdateMemberRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { memberId: string; role: string }) =>
      settingsApi.updateMemberRole(input.memberId, input.role),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tenant"] });
    },
  });
}

export function useRemoveMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) => settingsApi.removeMember(memberId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tenant"] });
    },
  });
}

/** ADMIN-gated list — pass enabled:false to skip fetching for non-admins. */
export function useInvitations(options?: { enabled?: boolean }) {
  return useCursorList(
    ["tenant", "invitations"],
    (cursor) => settingsApi.listInvitations(cursor),
    { enabled: options?.enabled },
  );
}

export function useCreateInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { email: string; role: string }) =>
      settingsApi.createInvitation(input),
    onSuccess: () => {
      // An invitation also creates a pending member — refresh both lists.
      void queryClient.invalidateQueries({ queryKey: ["tenant"] });
    },
  });
}

export function useRevokeInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (invitationId: string) => settingsApi.revokeInvitation(invitationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tenant"] });
    },
  });
}

// --- UBB platform bill ------------------------------------------------------

export function useBillingPeriods() {
  return useCursorList(["tenant", "billing-periods"], (cursor) =>
    settingsApi.listBillingPeriods(cursor),
  );
}

export function useTenantInvoices() {
  return useCursorList(["tenant", "invoices"], (cursor) =>
    settingsApi.listTenantInvoices(cursor),
  );
}

// --- Audit ledger -----------------------------------------------------------

export function useAuditRecords(filters: AuditFilters) {
  return useCursorList(["audit", "records", filters], (cursor) =>
    settingsApi.listAuditRecords(filters, cursor),
  );
}
