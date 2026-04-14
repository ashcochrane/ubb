// src/features/reconciliation/api/queries.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { reconciliationApi } from "./provider";
import type {
  EditPricesRequest,
  AdjustBoundaryRequest,
  InsertPeriodRequest,
  RecordAdjustmentRequest,
} from "./types";

export function useReconciliation(cardId: string) {
  return useQuery({
    queryKey: ["reconciliation", cardId],
    queryFn: () => reconciliationApi.getReconciliation(cardId),
    enabled: !!cardId,
  });
}

function useInvalidateReconciliation(cardId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["reconciliation", cardId] });
}

export function useEditPrices(cardId: string) {
  const invalidate = useInvalidateReconciliation(cardId);
  return useMutation({
    mutationFn: (req: EditPricesRequest) => reconciliationApi.editPrices(req),
    onSuccess: invalidate,
    onError: toastOnError("Couldn't apply price correction"),
  });
}

export function useAdjustBoundary(cardId: string) {
  const invalidate = useInvalidateReconciliation(cardId);
  return useMutation({
    mutationFn: (req: AdjustBoundaryRequest) => reconciliationApi.adjustBoundary(req),
    onSuccess: invalidate,
    onError: toastOnError("Couldn't adjust version boundary"),
  });
}

export function useInsertPeriod(cardId: string) {
  const invalidate = useInvalidateReconciliation(cardId);
  return useMutation({
    mutationFn: (req: InsertPeriodRequest) => reconciliationApi.insertPeriod(req),
    onSuccess: invalidate,
    onError: toastOnError("Couldn't insert pricing period"),
  });
}

export function useRecordAdjustment(cardId: string) {
  const invalidate = useInvalidateReconciliation(cardId);
  return useMutation({
    mutationFn: (req: RecordAdjustmentRequest) => reconciliationApi.recordAdjustment(req),
    onSuccess: invalidate,
    onError: toastOnError("Couldn't record adjustment"),
  });
}
