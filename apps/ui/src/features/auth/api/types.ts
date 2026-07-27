import type { TenantSchemas } from "@/api/types";

/**
 * Tenant configuration is the source of identity for the admin app. The
 * pre-refactor `/platform/me` endpoint no longer exists; tenant context is now
 * read from `GET /tenant/config` — products, billing mode, Stripe connection,
 * default currency, enforcement — while the signed-in Clerk user supplies
 * personal identity (name/email/avatar via <UserButton/>).
 */
export type TenantConfig = TenantSchemas["TenantConfigOut"];

export interface Me {
  tenant: TenantConfig;
}
