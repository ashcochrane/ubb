// src/api/types.ts
//
// Shortcut for consuming generated component schemas from each namespace.
// Use like: `type Customer = PlatformSchemas["CustomerDetailResponse"]`.

import type { components as BillingComponents } from "./generated/billing";
import type { components as MeComponents } from "./generated/me";
import type { components as MeteringComponents } from "./generated/metering";
import type { components as PlatformComponents } from "./generated/platform";
import type { components as TenantComponents } from "./generated/tenant";

export type PlatformSchemas = PlatformComponents["schemas"];
export type MeteringSchemas = MeteringComponents["schemas"];
export type BillingSchemas = BillingComponents["schemas"];
export type TenantSchemas = TenantComponents["schemas"];
export type MeSchemas = MeComponents["schemas"];
