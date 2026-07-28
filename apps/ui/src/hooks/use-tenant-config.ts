// The console bootstrap: GET /api/v1/tenant/config carries the two fields
// that gate the whole UI — `billing_mode` (meter_only | prepaid | postpaid)
// and `products` (metering | billing | subscriptions | referrals |
// metering_async) — plus enforcement posture, floors, and the workspace
// currency. There is no console "/me" endpoint; this is the source of truth.

import { queryOptions, useQuery } from "@tanstack/react-query";

import { tenantApi } from "@/api/client";
import { unwrap } from "@/api/problem";
import type { TenantSchemas } from "@/api/types";
import { API_PROVIDER, mockDelay } from "@/lib/api-provider";
import type { Product } from "@/lib/labels";

export type TenantConfig = TenantSchemas["TenantConfigOut"];

// Mock-mode config is a mutable module store so every observer of the
// ["tenant","config"] cache entry (nav shell, gates, the settings page's own
// provider) reads and writes ONE source of truth — a settings mutation in
// mock mode must never be reverted by another observer's refetch.
let mockTenantConfig: TenantConfig = {
  name: "Acme AI",
  billing_mode: "prepaid",
  products: ["metering", "billing", "subscriptions", "referrals", "metering_async"],
  require_cost_card_coverage: false,
  default_currency: "usd",
  stripe_connected_account_id: "acct_mock123",
  is_active: true,
  automatic_tax_enabled: false,
  enforcement_mode: "enforcing",
  arrival_signals_enabled: true,
  min_balance_micros: 0,
  soft_min_balance_micros: null,
  default_task_provider_cost_limit_micros: null,
};

/** Mock-mode only: current mock workspace config (returns a copy). */
export function readMockTenantConfig(): TenantConfig {
  return { ...mockTenantConfig };
}

/** Mock-mode only: replace the mock workspace config (used by feature mocks). */
export function writeMockTenantConfig(next: TenantConfig): void {
  mockTenantConfig = { ...next };
}

async function fetchTenantConfig(): Promise<TenantConfig> {
  if (API_PROVIDER === "mock") {
    await mockDelay();
    return readMockTenantConfig();
  }
  return unwrap(await tenantApi.GET("/config"));
}

export const tenantConfigQueryOptions = queryOptions({
  queryKey: ["tenant", "config"] as const,
  queryFn: fetchTenantConfig,
  staleTime: 5 * 60_000,
});

export function useTenantConfig() {
  return useQuery(tenantConfigQueryOptions);
}

export function hasProduct(
  config: TenantConfig | undefined,
  product: Product,
): boolean {
  return config?.products.includes(product) ?? false;
}

/** Product gate as a hook; false while config is loading. */
export function useHasProduct(product: Product): boolean {
  const { data } = useTenantConfig();
  return hasProduct(data, product);
}

/** Workspace currency (lowercase ISO); "usd" until config resolves. */
export function useTenantCurrency(): string {
  const { data } = useTenantConfig();
  return data?.default_currency ?? "usd";
}
