// src/features/reconciliation/api/mock.ts
import type {
  ReconciliationData,
  EditPricesRequest,
  AdjustBoundaryRequest,
  InsertPeriodRequest,
  RecordAdjustmentRequest,
} from "./types";
import { mockReconciliationData } from "./mock-data";
import { mockDelay } from "@/lib/api-provider";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function getReconciliation(_cardId: string): Promise<ReconciliationData> {
  await mockDelay();
  return structuredClone(mockReconciliationData);
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function editPrices(_req: EditPricesRequest): Promise<{ success: boolean }> {
  await mockDelay(500);
  return { success: true };
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function adjustBoundary(_req: AdjustBoundaryRequest): Promise<{ success: boolean }> {
  await mockDelay(500);
  return { success: true };
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function insertPeriod(_req: InsertPeriodRequest): Promise<{ success: boolean }> {
  await mockDelay(500);
  return { success: true };
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function recordAdjustment(_req: RecordAdjustmentRequest): Promise<{ success: boolean }> {
  await mockDelay(500);
  return { success: true };
}
