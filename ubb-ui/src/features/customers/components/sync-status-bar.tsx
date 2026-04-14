// src/features/customers/components/sync-status-bar.tsx
import { Link } from "@tanstack/react-router";
import { cn } from "@/lib/utils";
import { formatRelativeDate } from "@/lib/format";
import { useTriggerSync } from "../api/queries";
import type { SyncStatus } from "../api/types";

interface SyncStatusBarProps {
  syncStatus: SyncStatus;
}

export function SyncStatusBar({ syncStatus }: SyncStatusBarProps) {
  const syncMutation = useTriggerSync();
  const isSyncing = syncStatus.syncing || syncMutation.isPending;

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-bg-surface px-3.5 py-2.5">
      <div className="flex items-center gap-2 text-[12px] text-text-secondary">
        <div
          className={cn(
            "h-2 w-2 rounded-full",
            syncStatus.connected ? "bg-green" : "bg-red",
          )}
        />
        <strong className="text-text-primary">
          {syncStatus.connected ? "Stripe connected" : "Stripe disconnected"}
        </strong>
        {syncStatus.lastSyncAt && (
          <span className="text-text-muted">
            Last synced {formatRelativeDate(syncStatus.lastSyncAt)}
          </span>
        )}
      </div>
      <div className="flex items-center gap-1.5">
        <button
          className="rounded-full border border-border-mid bg-bg-surface px-3 py-1 text-[12px] font-medium text-text-secondary hover:bg-bg-subtle hover:text-text-primary disabled:opacity-50"
          onClick={() => syncMutation.mutate()}
          disabled={isSyncing}
        >
          {isSyncing ? "Syncing..." : "Sync now"}
        </button>
        <Link
          to="/settings"
          className="rounded-full border border-border-mid bg-bg-surface px-3 py-1 text-[12px] font-medium text-text-secondary hover:bg-bg-subtle hover:text-text-primary"
        >
          Stripe settings
        </Link>
      </div>
    </div>
  );
}
