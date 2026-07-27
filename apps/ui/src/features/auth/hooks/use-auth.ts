import { useCallback, useMemo } from "react";
import { useMe } from "@/features/auth/api/queries";
import type { TenantConfig } from "@/features/auth/api/types";

/** Known product keys the tenant may have enabled (`tenant.products`). */
export type Product = "metering" | "billing" | "subscriptions" | "referrals";

/** Tenant billing posture (`tenant.billing_mode`). */
export type BillingMode = "meter_only" | "prepaid" | "postpaid";

export interface UseAuth {
  tenant: TenantConfig | null;
  tenantName: string | null;
  products: string[];
  billingMode: string | null;
  /** True when the tenant has a billing posture (prepaid/postpaid or billing product). */
  isBillingMode: boolean;
  /**
   * True only for `billing_mode === "prepaid"`. Prefer this (and
   * `isPostpaid`) over `isBillingMode` whenever the wallet-vs-invoice
   * mechanism actually differs — `isBillingMode` conflates the two.
   */
  isPrepaid: boolean;
  /**
   * True only for `billing_mode === "postpaid"`. Under postpaid the wallet
   * is not the billing mechanism: drawdown skips postpaid customers
   * entirely and both balance floors are skipped at the spend-control gate,
   * so prepaid-only wallet surfaces (top-up, withdraw, auto top-up, grants,
   * the min-balance floors) should be hidden rather than rendered inert.
   */
  isPostpaid: boolean;
  /** `Tenant.enforcement_mode` (`"off" | "enforcing"`), or null while loading. */
  enforcementMode: string | null;
  defaultCurrency: string;
  stripeConnected: boolean;
  /**
   * Whether a product/module is available. Unknown/empty product lists fall
   * open (show everything) so a misconfigured tenant is never locked out of
   * the whole app; an explicit non-empty list gates strictly.
   */
  hasProduct: (product: Product | string) => boolean;
}

export function useAuth(): UseAuth {
  const { data: me } = useMe();
  const tenant = me?.tenant ?? null;
  const products = useMemo(() => tenant?.products ?? [], [tenant]);
  const billingMode = tenant?.billing_mode ?? null;

  const hasProduct = useCallback(
    (product: Product | string) =>
      products.length === 0 || products.includes(product),
    [products],
  );

  const isPrepaid = billingMode === "prepaid";
  const isPostpaid = billingMode === "postpaid";
  const isBillingMode = isPrepaid || isPostpaid || products.includes("billing");

  return {
    tenant,
    tenantName: tenant?.name ?? null,
    products,
    billingMode,
    isBillingMode,
    isPrepaid,
    isPostpaid,
    enforcementMode: tenant?.enforcement_mode ?? null,
    defaultCurrency: tenant?.default_currency || "USD",
    stripeConnected: Boolean(tenant?.stripe_connected_account_id),
    hasProduct,
  };
}
