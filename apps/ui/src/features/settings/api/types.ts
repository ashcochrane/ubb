// Type aliases from the generated schema map, plus local interfaces for the
// contract's UNTYPED responses (additionalProperties: true) on this surface.

import type { PlatformSchemas, TenantSchemas } from "@/api/types";

export type TenantConfig = TenantSchemas["TenantConfigOut"];
export type TenantConfigPatch = TenantSchemas["TenantConfigIn"];
export type Member = TenantSchemas["MemberOut"];
export type Invitation = TenantSchemas["InvitationOut"];
export type BillingPeriod = TenantSchemas["TenantBillingPeriodOut"];
export type TenantInvoice = TenantSchemas["TenantInvoiceOut"];
export type AuditRecord = PlatformSchemas["AuditRecordOut"];

export interface AuditFilters {
  action?: string;
  resource_type?: string;
  resource_id?: string;
}

// ---------------------------------------------------------------------------
// Untyped responses — GET /connect/status and POST /connect/start return
// `additionalProperties: true` objects in the schema. The concrete shapes are
// recovered from the server source and narrowed here (never cast).

// [backend-verified shape — see discovery spec §4.2]
export interface ConnectStatus {
  /** Stripe account id ("" = not connected). */
  account_id: string;
  charges_enabled: boolean;
  /** account_id set AND charges_enabled. */
  onboarded: boolean;
}

// [backend-verified shape — see discovery spec §4.1]
export interface ConnectStartResult {
  /** Stripe OAuth URL to redirect the browser to. */
  authorize_url: string;
}

export function toConnectStatus(raw: Record<string, unknown>): ConnectStatus {
  return {
    account_id: typeof raw["account_id"] === "string" ? raw["account_id"] : "",
    charges_enabled: raw["charges_enabled"] === true,
    onboarded: raw["onboarded"] === true,
  };
}

export function toConnectStartResult(
  raw: Record<string, unknown>,
): ConnectStartResult {
  return {
    authorize_url:
      typeof raw["authorize_url"] === "string" ? raw["authorize_url"] : "",
  };
}
