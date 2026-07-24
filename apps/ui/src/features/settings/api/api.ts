// Real API implementation. Every call goes through unwrap() so failures
// always reject with a typed ApiProblem.

import { connectApi, rootApi, tenantApi } from "@/api/client";
import type { CursorPage } from "@/api/pagination";
import { unwrap } from "@/api/problem";

import {
  toConnectStartResult,
  toConnectStatus,
  type AuditFilters,
  type AuditRecord,
  type BillingPeriod,
  type ConnectStartResult,
  type ConnectStatus,
  type Invitation,
  type Member,
  type TenantConfig,
  type TenantConfigPatch,
  type TenantInvoice,
} from "./types";

// --- Workspace config -------------------------------------------------------

export async function getTenantConfig(): Promise<TenantConfig> {
  return unwrap(await tenantApi.GET("/config"));
}

/**
 * PATCH semantics: send ONLY changed fields. For the clearable fields
 * (soft_min_balance_micros, default_task_*_micros) an explicit null CLEARS
 * the value while an omitted key preserves it — callers build the patch with
 * that distinction and JSON serialisation drops only `undefined` keys.
 */
export async function updateTenantConfig(
  patch: TenantConfigPatch,
): Promise<TenantConfig> {
  return unwrap(await tenantApi.PATCH("/config", { body: patch }));
}

// --- Stripe Connect ---------------------------------------------------------

export async function getConnectStatus(): Promise<ConnectStatus> {
  return toConnectStatus(unwrap(await connectApi.GET("/status")));
}

export async function startConnect(
  returnUrl: string,
): Promise<ConnectStartResult> {
  return toConnectStartResult(
    unwrap(
      await connectApi.POST("/start", { body: { return_url: returnUrl } }),
    ),
  );
}

// --- Team -------------------------------------------------------------------

export async function listMembers(
  cursor?: string,
): Promise<CursorPage<Member>> {
  return unwrap(
    await tenantApi.GET("/members", { params: { query: { cursor } } }),
  );
}

export async function updateMemberRole(
  memberId: string,
  role: string,
): Promise<Member> {
  return unwrap(
    await tenantApi.PATCH("/members/{member_id}", {
      params: { path: { member_id: memberId } },
      body: { role },
    }),
  );
}

export async function removeMember(memberId: string): Promise<void> {
  unwrap(
    await tenantApi.DELETE("/members/{member_id}", {
      params: { path: { member_id: memberId } },
    }),
  );
}

export async function listInvitations(
  cursor?: string,
): Promise<CursorPage<Invitation>> {
  return unwrap(
    await tenantApi.GET("/invitations", { params: { query: { cursor } } }),
  );
}

export async function createInvitation(input: {
  email: string;
  role: string;
}): Promise<Invitation> {
  return unwrap(await tenantApi.POST("/invitations", { body: input }));
}

export async function revokeInvitation(invitationId: string): Promise<void> {
  unwrap(
    await tenantApi.DELETE("/invitations/{invitation_id}", {
      params: { path: { invitation_id: invitationId } },
    }),
  );
}

// --- UBB platform bill ------------------------------------------------------

export async function listBillingPeriods(
  cursor?: string,
): Promise<CursorPage<BillingPeriod>> {
  return unwrap(
    await tenantApi.GET("/billing-periods", { params: { query: { cursor } } }),
  );
}

export async function listTenantInvoices(
  cursor?: string,
): Promise<CursorPage<TenantInvoice>> {
  return unwrap(
    await tenantApi.GET("/invoices", { params: { query: { cursor } } }),
  );
}

// --- Audit ledger -----------------------------------------------------------

export async function listAuditRecords(
  filters: AuditFilters,
  cursor?: string,
): Promise<CursorPage<AuditRecord>> {
  return unwrap(
    await rootApi.GET("/audit/records", {
      params: {
        query: {
          action: filters.action || undefined,
          resource_type: filters.resource_type || undefined,
          resource_id: filters.resource_id || undefined,
          cursor,
        },
      },
    }),
  );
}
