import { useCallback } from "react";
import { useShallow } from "zustand/shallow";
import { useAuthStore, type TenantMode } from "@/stores/auth-store";

export interface UseAuth {
  activeTenantId: string | null;
  tenantMode: TenantMode | null;
  permissions: string[];
  hasPermission: (permission: string) => boolean;
  isBillingMode: boolean;
}

export function useAuth(): UseAuth {
  const { activeTenantId, tenantMode, permissions } = useAuthStore(
    useShallow((s) => ({
      activeTenantId: s.activeTenantId,
      tenantMode: s.tenantMode,
      permissions: s.permissions,
    })),
  );

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
