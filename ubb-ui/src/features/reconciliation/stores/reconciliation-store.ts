// src/features/reconciliation/stores/reconciliation-store.ts
import { create } from "zustand";

type PanelType = "edit-prices" | "adjust-boundary" | "insert-period" | "adjustments" | null;

interface ReconciliationStore {
  selectedVersionId: string | null;
  openPanel: PanelType;
  selectVersion: (id: string) => void;
  openPanelFor: (panel: PanelType) => void;
  closePanel: () => void;
  reset: () => void;
}

export const useReconciliationStore = create<ReconciliationStore>((set) => ({
  selectedVersionId: null,
  openPanel: null,
  selectVersion: (id) => set({ selectedVersionId: id, openPanel: null }),
  openPanelFor: (panel) => set({ openPanel: panel }),
  closePanel: () => set({ openPanel: null }),
  reset: () => set({ selectedVersionId: null, openPanel: null }),
}));
