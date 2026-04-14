// src/features/reconciliation/api/api.ts
import type {
  ReconciliationData,
  EditPricesRequest,
  AdjustBoundaryRequest,
  InsertPeriodRequest,
  RecordAdjustmentRequest,
} from "./types";
import { meteringApi } from "@/api/client";

export async function getReconciliation(cardId: string): Promise<ReconciliationData> {
  const { data } = await meteringApi.GET("/rate-cards/{cardId}/reconciliation", { params: { path: { cardId } } });
  return data as ReconciliationData;
}

export async function editPrices(req: EditPricesRequest): Promise<{ success: boolean }> {
  const { data } = await meteringApi.POST("/rate-cards/reconciliation/edit-prices", { body: req });
  return data as { success: boolean };
}

export async function adjustBoundary(req: AdjustBoundaryRequest): Promise<{ success: boolean }> {
  const { data } = await meteringApi.POST("/rate-cards/reconciliation/adjust-boundary", { body: req });
  return data as { success: boolean };
}

export async function insertPeriod(req: InsertPeriodRequest): Promise<{ success: boolean }> {
  const { data } = await meteringApi.POST("/rate-cards/reconciliation/insert-period", { body: req });
  return data as { success: boolean };
}

export async function recordAdjustment(req: RecordAdjustmentRequest): Promise<{ success: boolean }> {
  const { data } = await meteringApi.POST("/rate-cards/reconciliation/record-adjustment", { body: req });
  return data as { success: boolean };
}
