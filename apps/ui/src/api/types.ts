// src/api/types.ts
//
// Shortcut for consuming generated component schemas from the canonical API.
// Use like: `type Customer = PlatformSchemas["CustomerDetailResponse"]`.

import type { components as ApiComponents } from "./generated/api";

type ApiSchemas = ApiComponents["schemas"];

export type PlatformSchemas = ApiSchemas;
export type MeteringSchemas = ApiSchemas;
export type BillingSchemas = ApiSchemas;
export type TenantSchemas = ApiSchemas;
export type MeSchemas = ApiSchemas;
export type SubscriptionSchemas = ApiSchemas;
export type MarginSchemas = ApiSchemas;
export type ReferralSchemas = ApiSchemas;
export type WebhookSchemas = ApiSchemas;
export type AuditSchemas = ApiSchemas;
