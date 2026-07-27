import type { TenantSchemas } from "@/api/types";

export type TenantConfig = TenantSchemas["TenantConfigOut"];
export type TenantConfigUpdate = TenantSchemas["TenantConfigIn"];

export type ApiKey = TenantSchemas["ApiKeyOut"];
export type ApiKeyCreate = TenantSchemas["ApiKeyCreateIn"];

export type Member = TenantSchemas["MemberOut"];
export type MemberRoleUpdate = TenantSchemas["MemberRoleUpdateIn"];

export type Invitation = TenantSchemas["InvitationOut"];
export type InvitationCreate = TenantSchemas["InvitationCreateIn"];

export type ConnectStart = TenantSchemas["ConnectStartIn"];
export type SandboxReset = TenantSchemas["SandboxResetIn"];

/**
 * A handful of endpoints (api-key create/rotate, connect start/status, sandbox
 * get/create) are typed as an open `object` in the OpenAPI spec — the backend
 * returns a raw dict. We surface them as `Record<string, unknown>` and narrow
 * defensively at the call site. The known field aliases below document what we
 * probe for; none is guaranteed to be present.
 */
export type UntypedObject = Record<string, unknown>;

/** Pull the one-time raw key out of an api-key create/rotate response. */
export function readRawKey(obj: UntypedObject): string | null {
  for (const field of ["key", "api_key", "secret", "token", "raw_key"]) {
    const v = obj[field];
    if (typeof v === "string" && v.length > 0) return v;
  }
  return null;
}

/** Pull the Stripe onboarding redirect url out of a connect/start response. */
export function readConnectUrl(obj: UntypedObject): string | null {
  for (const field of ["url", "onboarding_url", "account_link_url", "link"]) {
    const v = obj[field];
    if (typeof v === "string" && v.length > 0) return v;
  }
  return null;
}

/** Pull a human string value from an untyped object for a given field. */
export function readString(obj: UntypedObject, field: string): string | null {
  const v = obj[field];
  return typeof v === "string" && v.length > 0 ? v : null;
}

/** Pull a boolean value from an untyped object for a given field. */
export function readBool(obj: UntypedObject, field: string): boolean | null {
  const v = obj[field];
  return typeof v === "boolean" ? v : null;
}
