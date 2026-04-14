// src/features/reconciliation/components/timeline.tsx
import { useMemo } from "react";
import type { TimelineData, TimelineSegment } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";
import { cn } from "@/lib/utils";

interface TimelineProps {
  timeline: TimelineData;
}

export function Timeline({ timeline }: TimelineProps) {
  const selectedVersionId = useReconciliationStore((s) => s.selectedVersionId);
  const selectVersion = useReconciliationStore((s) => s.selectVersion);

  const dateMarkers = useMemo(
    () => timeline.dateMarkers.map((d) => ({ key: d, label: d })),
    [timeline.dateMarkers],
  );

  return (
    <div className="space-y-2">
      {/* Legend */}
      <div className="flex gap-4 text-muted text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: "#5DCAA5" }} /> Active
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: "#D3D1C7" }} /> Superseded
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: "#85B7EB" }} /> Retroactive
        </span>
      </div>

      {/* Original track */}
      <div>
        <div className="mb-1 text-label text-muted-foreground">
          As originally tracked: <span className="font-mono font-medium">${timeline.originalTotal.toLocaleString()}</span>
        </div>
        <TrackBar
          segments={timeline.originalTrack}
          selectedVersionId={selectedVersionId}
          onSelect={selectVersion}
          dashed
        />
      </div>

      {/* Connector */}
      <div className="flex items-center gap-2 px-2">
        <div className="h-px flex-1 border-t border-dashed border-border" />
        <span className="text-muted text-muted-foreground">
          {timeline.adjustmentTotal >= 0 ? "+" : ""}${timeline.adjustmentTotal.toFixed(2)} adjustments
        </span>
        <div className="h-px flex-1 border-t border-dashed border-border" />
      </div>

      {/* Reconciled track */}
      <div>
        <div className="mb-1 text-label text-muted-foreground">
          Reconciled timeline: <span className="font-mono font-medium">${timeline.reconciledTotal.toLocaleString()}</span>
        </div>
        <TrackBar
          segments={timeline.reconciledTrack}
          selectedVersionId={selectedVersionId}
          onSelect={selectVersion}
        />
      </div>

      {/* Date markers */}
      <div className="flex justify-between px-1 text-tiny text-muted-foreground">
        {dateMarkers.map((d) => (
          <span key={d.key}>{d.label}</span>
        ))}
      </div>
    </div>
  );
}

function TrackBar({
  segments,
  selectedVersionId,
  onSelect,
  dashed,
}: {
  segments: TimelineSegment[];
  selectedVersionId: string | null;
  onSelect: (id: string) => void;
  dashed?: boolean;
}) {
  return (
    <div className="flex gap-0.5">
      {segments.map((seg) => {
        const isSelected = selectedVersionId === seg.versionId;
        return (
          <button
            key={seg.id}
            type="button"
            onClick={() => onSelect(seg.versionId)}
            className={cn(
              "flex h-9 items-center justify-center rounded-md px-2 text-label font-medium transition-all",
              dashed && "border border-dashed",
              !dashed && "border",
              isSelected && "outline outline-2 outline-offset-1 outline-foreground",
            )}
            style={{
              flex: seg.flex,
              backgroundColor: seg.color,
              borderColor: dashed ? "rgba(0,0,0,0.15)" : "transparent",
              color: seg.color === "#F1EFE8" ? "#888780" : "#1a1a1a",
            }}
          >
            <span className="mr-1 text-muted opacity-70">{seg.label}</span>
            <span className="font-mono text-muted">${seg.cost}</span>
          </button>
        );
      })}
    </div>
  );
}
