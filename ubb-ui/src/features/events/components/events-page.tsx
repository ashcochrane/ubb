import { useCallback, useMemo, useState } from "react";
import { Download } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useEventFilterOptions,
  useEvents,
  useAuditTrail,
  usePushEvents,
  useReverseAuditEntry,
  useExportEventsCsv,
} from "../api/queries";
import type { EventFilters, StagedEvent } from "../api/types";
import { FilterStrip } from "./filter-strip";
import { AddDataStrip, type AddMode } from "./add-data-strip";
import { PasteArea } from "./paste-area";
import { UploadZone } from "./upload-zone";
import { StagingSection } from "./staging-section";
import { StatusBar } from "./status-bar";
import { EventsTable } from "./events-table";
import { AuditTrail } from "./audit-trail";

type DatePreset = "7d" | "30d" | "90d" | "all";

export function EventsPage() {
  const { data: filterOptions, isLoading } = useEventFilterOptions();

  const [filters, setFilters] = useState<EventFilters>({
    dateFrom: "2026-02-18",
    dateTo: "2026-03-20",
    customerKey: "",
    groupKey: "",
    cardKey: "",
  });
  const [datePreset, setDatePreset] = useState<DatePreset | null>("30d");

  const { data: eventsData } = useEvents(filterOptions ? filters : null);
  const { data: auditEntries } = useAuditTrail();

  const [addMode, setAddMode] = useState<AddMode>(null);
  const [stagedEvents, setStagedEvents] = useState<StagedEvent[]>([]);
  const [reason, setReason] = useState("");
  const [pushResult, setPushResult] = useState<string | null>(null);
  const [showRecorded, setShowRecorded] = useState(false);
  const [eventOverrides, setEventOverrides] = useState<Record<number, Partial<{ customerKey: string; groupKey: string }>>>({});

  const pushMutation = usePushEvents();
  const reverseMutation = useReverseAuditEntry();
  const exportMutation = useExportEventsCsv();

  const handleModeChange = useCallback((mode: AddMode) => {
    setAddMode(mode);
    if (mode === "row" && stagedEvents.length === 0) {
      setStagedEvents([{ timestamp: "2026-03-20", customerKey: "", groupKey: "", cardKey: "", dimension: "", quantity: 0 }]);
    }
  }, [stagedEvents.length]);

  const handlePaste = useCallback((rows: string[][]) => {
    const parsed: StagedEvent[] = rows.map((p) => ({
      timestamp: p[0] ?? "",
      customerKey: p[1] ?? "",
      groupKey: p[2] ?? "",
      cardKey: p[3] ?? "",
      dimension: p[4] ?? "",
      quantity: parseFloat(p[5] ?? "0") || 0,
    }));
    setStagedEvents((prev) => [...prev, ...parsed]);
    setAddMode(null);
  }, []);

  const handleFileContent = useCallback((content: string) => {
    const rows = content.trim().split("\n").filter((l) => l.trim()).map((l) => l.split("\t"));
    handlePaste(rows);
  }, [handlePaste]);

  const handleAddRow = useCallback(() => {
    setStagedEvents((prev) => [...prev, { timestamp: "2026-03-20", customerKey: "", groupKey: "", cardKey: "", dimension: "", quantity: 0 }]);
  }, []);

  const handleClearStaged = useCallback(() => {
    setStagedEvents([]);
    setAddMode(null);
  }, []);

  const handlePush = useCallback(() => {
    pushMutation.mutate(
      { events: stagedEvents, reason },
      {
        onSuccess: (result) => {
          setPushResult(`Pushed ${result.pushedCount} rows`);
          setTimeout(() => {
            setStagedEvents([]);
            setReason("");
            setPushResult(null);
            setAddMode(null);
          }, 1200);
        },
      },
    );
  }, [pushMutation, stagedEvents, reason]);

  const handleExport = useCallback(() => {
    exportMutation.mutate(filters);
  }, [exportMutation, filters]);

  const displayEvents = useMemo(() => {
    if (!eventsData) return [];
    return eventsData.events.map((ev, i) => ({
      ...ev,
      ...eventOverrides[i],
    }));
  }, [eventsData, eventOverrides]);

  if (isLoading || !filterOptions) {
    return (
      <div className="space-y-5 px-10 pt-8 pb-20">
        <PageHeader title="Events" />
        <Skeleton className="h-12 rounded-md" />
        <Skeleton className="h-16 rounded-md" />
        <Skeleton className="h-64 rounded-md" />
      </div>
    );
  }

  const showStaging = stagedEvents.length > 0 || addMode === "row";

  return (
    <div className="space-y-5 px-10 pt-8 pb-20">
      <PageHeader
        title="Events"
        actions={
          <button
            className="inline-flex items-center gap-1.5 rounded-full border border-border-mid bg-bg-surface px-3 py-[5px] text-[11px] font-medium text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
            onClick={handleExport}
            disabled={exportMutation.isPending}
          >
            <Download className="h-[11px] w-[11px]" />
            {exportMutation.isPending
              ? "Generating..."
              : exportMutation.isSuccess
                ? "Download ready"
                : "Export CSV"}
          </button>
        }
      />

      <FilterStrip
        filterOptions={filterOptions}
        filters={filters}
        onFiltersChange={setFilters}
        datePreset={datePreset}
        onDatePresetChange={setDatePreset}
      />

      <AddDataStrip mode={addMode} onModeChange={handleModeChange} />

      {addMode === "paste" && (
        <PasteArea onParse={handlePaste} onCancel={() => setAddMode(null)} />
      )}
      {addMode === "upload" && <UploadZone onFileContent={handleFileContent} />}

      {showStaging && (
        <StagingSection
          events={stagedEvents}
          filterOptions={filterOptions}
          reason={reason}
          onReasonChange={setReason}
          onEventsChange={setStagedEvents}
          onAddRow={handleAddRow}
          onClearAll={handleClearStaged}
          onPush={handlePush}
          isPushing={pushMutation.isPending}
          pushResult={pushResult}
        />
      )}

      {eventsData && (
        <>
          <StatusBar
            totalCount={eventsData.totalCount}
            totalCostDollars={eventsData.totalCostDollars}
            estimatedCsvBytes={eventsData.estimatedCsvBytes}
            showRecorded={showRecorded}
            onToggleRecorded={() => setShowRecorded((v) => !v)}
          />

          <EventsTable
            events={displayEvents}
            filterOptions={filterOptions}
            onUpdateEvent={(idx, field, value) => {
              setEventOverrides((prev) => ({
                ...prev,
                [idx]: { ...prev[idx], [field]: value },
              }));
            }}
          />
          <div className="text-[10px] text-text-muted">Scroll to load more rows</div>
        </>
      )}

      {auditEntries && (
        <AuditTrail
          entries={auditEntries}
          onViewBatch={() => {}}
          onReverseBatch={(id) => reverseMutation.mutate(id)}
          reversingId={reverseMutation.isPending ? (reverseMutation.variables ?? null) : null}
        />
      )}
    </div>
  );
}
