// src/api/types.ts
//
// Shortcut for consuming generated component schemas from the canonical API.
// Use like: `type Balance = BillingSchemas["BalanceResponse"]`.
// All aliases point at the same generated schema map; the per-namespace names
// exist to keep feature imports self-documenting.

import type { components as ApiComponents } from "./generated/api";

type ApiSchemas = ApiComponents["schemas"];

// The kernel surfaces mounted directly under /api/v1, which `rootApi` calls
// and which no product prefix owns — the unit-of-work lifecycle among them
// (#409). It has been a client without a matching schema alias until now, and
// naming it is what stops a kernel shape being imported under a product's
// name.
export type RootSchemas = ApiSchemas;
export type PlatformSchemas = ApiSchemas;
export type MeteringSchemas = ApiSchemas;
export type BillingSchemas = ApiSchemas;
export type TenantSchemas = ApiSchemas;
export type MarginSchemas = ApiSchemas;
export type WebhookSchemas = ApiSchemas;
export type ReferralSchemas = ApiSchemas;
export type SubscriptionSchemas = ApiSchemas;
