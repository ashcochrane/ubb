import { create } from "zustand";

export type TenantMode = "track" | "revenue" | "billing";

interface AuthState {
  activeTenantId: string | null;
  tenantMode: TenantMode | null;
  permissions: string[];

  setTenant: (tenantId: string, mode: TenantMode) => void;
  setPermissions: (permissions: string[]) => void;
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  activeTenantId: null,
  tenantMode: null,
  permissions: [],

  setTenant: (tenantId, mode) =>
    set({ activeTenantId: tenantId, tenantMode: mode }),

  setPermissions: (permissions) => set({ permissions }),

  reset: () =>
    set({ activeTenantId: null, tenantMode: null, permissions: [] }),
}));
