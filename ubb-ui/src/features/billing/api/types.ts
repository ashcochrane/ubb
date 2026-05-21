// src/features/billing/api/types.ts
import type { PlatformSchemas } from "@/api/types";

export type DefaultMargin = PlatformSchemas["TenantDefaultMarginResponse"];
export type UpdateDefaultMarginRequest =
  PlatformSchemas["UpdateTenantDefaultMarginRequest"];
