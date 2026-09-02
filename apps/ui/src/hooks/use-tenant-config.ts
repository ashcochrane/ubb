// The console bootstrap: GET /api/v1/tenant/config carries the two fields
// that gate the whole UI — `billing_mode` (meter_only | prepaid | postpaid)
// and `products` (metering | billing | referrals — the closed set the
// contract enumerates) — plus enforcement posture, floors, and the workspace
// currency. There is no console "/me" endpoint; this is the source of truth.

import { queryOptions, useQuery } from "@tanstack/react-query";

import { tenantApi } from "@/api/client";
import { unwrap } from "@/api/problem";
import type { TenantSchemas } from "@/api/types";
import { API_PROVIDER, mockDelay } from "@/lib/api-provider";
import type { TenantProduct } from "@/lib/vocabulary";

export type TenantConfig = TenantSchemas["TenantConfigOut"];

// Mock-mode config is a mutable module store so every observer of the
// ["tenant","config"] cache entry (nav shell, gates, the settings page's own
// provider) reads and writes ONE source of truth — a settings mutation in
// mock mode must never be reverted by another observer's refetch.
let mockTenantConfig: TenantConfig = {
  name: "Acme AI",
  billing_mode: "prepaid",
  products: ["metering", "billing", "referrals"],
  default_currency: "usd",
  stripe_connected_account_id: "acct_mock123",
  is_active: true,
  automatic_tax_enabled: false,
  enforcement_mode: "enforcing",
  live_counter_maintenance_enabled: true,
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
  product: TenantProduct,
): boolean {
  return config?.products.includes(product) ?? false;
}

/** Product gate as a hook; false while config is loading. */
export function useHasProduct(product: TenantProduct): boolean {
  const { data } = useTenantConfig();
  return hasProduct(data, product);
}

/** Workspace currency (lowercase ISO); "usd" until config resolves. */
export function useTenantCurrency(): string {
  const { data } = useTenantConfig();
  return data?.default_currency ?? "usd";
}

/**
 * Postpaid: usage drawdown skips the wallet entirely and both balance floors
 * (`min_balance_micros` / `soft_min_balance_micros`) are ignored by the spend
 * gate (apps/billing/gating risk_service; apps/billing/wallets/operations
 * debit()). Wallet-only surfaces — top-up, withdraw, auto-top-up, credit
 * grants, and the floor fields themselves — are inert under this mode and
 * should explain their absence rather than render as live controls.
 *
 * Deliberately a NARROWER flag than `billing_mode` itself (which other call
 * sites branch on directly, e.g. `=== "meter_only"`) — this only ever means
 * "the wallet isn't the billing mechanism," never anything about meter_only.
 */
export function isPostpaid(config: TenantConfig | undefined): boolean {
  return config?.billing_mode === "postpaid";
}

/** Postpaid gate as a hook; false while config is loading. */
export function useIsPostpaid(): boolean {
  const { data } = useTenantConfig();
  return isPostpaid(data);
}

/**
 * The posture in which a workspace meters and never bills, as the wire spells
 * it today.
 *
 * ⚠ SPELLED HERE AND NOWHERE NEW. The value is a retired word (slice 8 renames
 * it to `external`, the fact a tenant is actually choosing) with a console
 * ledger seat that is a CEILING on how many files may carry it — so a feature
 * that needs to ask the question imports this predicate rather than comparing
 * the string itself, and the rename becomes one line here instead of one per
 * caller. This file already carried the word, which is why the predicate lives
 * beside `isPostpaid` rather than in the feature that first needed it (#423).
 */
export const METERING_ONLY_BILLING_MODE: TenantConfig["billing_mode"] = "meter_only";

/**
 * Whether the workspace meters without billing.
 *
 * The posture decides what a declaration DOES rather than what it says: a
 * fixed-price kind of work is recorded and inert for a workspace that does not
 * bill, and becomes a start-gate refusal the day billing is enabled (#187 §9).
 * Deliberately the sibling of `isPostpaid` above and just as narrow.
 */
export function isMeteringOnly(config: TenantConfig | undefined): boolean {
  return config?.billing_mode === METERING_ONLY_BILLING_MODE;
}

/** Metering-only posture as a hook; false while config is loading. */
export function useIsMeteringOnly(): boolean {
  const { data } = useTenantConfig();
  return isMeteringOnly(data);
}
