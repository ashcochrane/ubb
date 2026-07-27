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

  const isBillingMode =
    billingMode === "prepaid" ||
    billingMode === "postpaid" ||
    products.includes("billing");

  return {
    tenant,
    tenantName: tenant?.name ?? null,
    products,
    billingMode,
    isBillingMode,
    defaultCurrency: tenant?.default_currency || "USD",
    stripeConnected: Boolean(tenant?.stripe_connected_account_id),
    hasProduct,
  };
}
