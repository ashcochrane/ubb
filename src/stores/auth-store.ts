import { create } from "zustand";

interface AuthState {
  permissions: string[];
  setPermissions: (permissions: string[]) => void;
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  permissions: [],
  setPermissions: (permissions) => set({ permissions }),
  reset: () => set({ permissions: [] }),
}));
