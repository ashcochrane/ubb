// src/features/reconciliation/components/reconciliation-page.tsx
import { useCallback, useEffect } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useReconciliation, useEditPrices, useAdjustBoundary, useInsertPeriod, useRecordAdjustment } from "../api/queries";
import type { RecordAdjustmentRequest } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";
import { CardHeader } from "./card-header";
import { Timeline } from "./timeline";
import { VersionDetail } from "./version-detail";
import { EditPricesPanel } from "./edit-prices-panel";
import { AdjustBoundaryPanel } from "./adjust-boundary-panel";
import { InsertPeriodPanel } from "./insert-period-panel";
import { AdjustmentsSection } from "./adjustments-section";
import { ReconciliationSummary } from "./reconciliation-summary";
import { AuditTrail } from "./audit-trail";

interface ReconciliationPageProps {
  cardId: string;
}

export function ReconciliationPage({ cardId }: ReconciliationPageProps) {
  const { data, isLoading } = useReconciliation(cardId);
  const selectedVersionId = useReconciliationStore((s) => s.selectedVersionId);
  const openPanel = useReconciliationStore((s) => s.openPanel);
  const selectVersion = useReconciliationStore((s) => s.selectVersion);
  const reset = useReconciliationStore((s) => s.reset);
  const editPrices = useEditPrices(cardId);
  const adjustBoundary = useAdjustBoundary(cardId);
  const insertPeriod = useInsertPeriod(cardId);
  const recordAdjustment = useRecordAdjustment(cardId);

  // Reset store when navigating to a different card
  useEffect(() => {
    reset();
  }, [cardId, reset]);

  // Auto-select the active version on load
  useEffect(() => {
    if (data && !selectedVersionId) {
      const active = data.versions.find((v) => v.status === "active");
      if (active) selectVersion(active.id);
    }
  }, [data, selectedVersionId, selectVersion]);

  const editPricesMutateAsync = editPrices.mutateAsync;
  const adjustBoundaryMutateAsync = adjustBoundary.mutateAsync;
  const insertPeriodMutateAsync = insertPeriod.mutateAsync;
  const recordAdjustmentMutateAsync = recordAdjustment.mutateAsync;

  const handleEditPricesApply = useCallback(
    async (newPrices: Record<string, number>, reason: string) => {
      if (!selectedVersionId) return;
      await editPricesMutateAsync({ versionId: selectedVersionId, newPrices, reason });
    },
    [editPricesMutateAsync, selectedVersionId],
  );

  const nextVersionId =
    data && selectedVersionId
      ? data.versions[data.versions.findIndex((v) => v.id === selectedVersionId) + 1]?.id ?? ""
      : "";

  const handleAdjustBoundaryApply = useCallback(
    async (newDate: string, newTime: string, reason: string) => {
      if (!selectedVersionId) return;
      await adjustBoundaryMutateAsync({
        fromVersionId: selectedVersionId,
        toVersionId: nextVersionId,
        newBoundaryDate: newDate,
        newBoundaryTime: newTime,
        reason,
      });
    },
    [adjustBoundaryMutateAsync, selectedVersionId, nextVersionId],
  );

  const handleInsertPeriodApply = useCallback(
    async (
      versionId: string,
      splitDate: string,
      splitTime: string,
      newPrices: Record<string, number>,
      reason: string,
    ) => {
      await insertPeriodMutateAsync({ versionId, splitDate, splitTime, newPrices, reason });
    },
    [insertPeriodMutateAsync],
  );

  const handleRecordAdjustment = useCallback(
    async (adjData: RecordAdjustmentRequest) => {
      await recordAdjustmentMutateAsync(adjData);
    },
    [recordAdjustmentMutateAsync],
  );

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-24 rounded-md" />
        <div className="grid grid-cols-4 gap-2.5">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-40 rounded-md" />
      </div>
    );
  }

  const selectedVersion = data.versions.find((v) => v.id === selectedVersionId);
  const selectedIdx = data.versions.findIndex((v) => v.id === selectedVersionId);
  const nextVersion = selectedIdx >= 0 ? data.versions[selectedIdx + 1] : undefined;

  return (
    <div className="space-y-5">
      <CardHeader data={data} />

      <Timeline timeline={data.timeline} />

      {selectedVersion && (
        <>
          <VersionDetail version={selectedVersion} />

          {openPanel === "edit-prices" && (
            <EditPricesPanel
              version={selectedVersion}
              onApply={handleEditPricesApply}
            />
          )}

          {openPanel === "adjust-boundary" && (
            <AdjustBoundaryPanel
              version={selectedVersion}
              nextVersion={nextVersion}
              onApply={handleAdjustBoundaryApply}
            />
          )}

          {openPanel === "insert-period" && (
            <InsertPeriodPanel
              version={selectedVersion}
              versions={data.versions}
              onApply={handleInsertPeriodApply}
            />
          )}
        </>
      )}

      <AdjustmentsSection onRecord={handleRecordAdjustment} />

      <ReconciliationSummary
        original={data.stats.originalTracked}
        reconciled={data.stats.reconciledTotal}
        delta={data.stats.netAdjustments}
      />

      <AuditTrail entries={data.auditTrail} />
    </div>
  );
}
