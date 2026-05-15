import { useCallback } from "react";
import { useMe } from "@/features/auth/api/queries";
import { useAuthStore } from "@/stores/auth-store";

export type TenantMode = "track" | "revenue" | "billing";

export interface UseAuth {
  activeTenantId: string | null;
  tenantMode: TenantMode | null;
  permissions: string[];
  hasPermission: (permission: string) => boolean;
  isBillingMode: boolean;
}

function deriveMode(products: string[] | undefined): TenantMode | null {
  if (!products) return null;
  if (products.includes("billing")) return "billing";
  if (products.includes("subscriptions")) return "revenue";
  return "track";
}

export function useAuth(): UseAuth {
  const { data: me } = useMe();
  const permissions = useAuthStore((s) => s.permissions);

  const activeTenantId = me?.tenant?.id ?? null;
  const tenantMode = deriveMode(me?.tenant?.products);

  const hasPermission = useCallback(
    (permission: string) => permissions.includes(permission),
    [permissions],
  );

  return {
    activeTenantId,
    tenantMode,
    permissions,
    hasPermission,
    isBillingMode: tenantMode === "billing",
  };
}
