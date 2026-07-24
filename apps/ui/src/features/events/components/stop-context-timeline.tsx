// The event's stop context: one entry per limit the event landed past.
// `arrived_after: false` marks the tipping event that crossed the limit;
// `true` marks a late arrival past an existing stop.

import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/format";
import { stopReasonLabel, stopScopeLabel } from "@/lib/labels";

import { shortId } from "../lib/search";
import type { StopContextEntry } from "../api/types";

export function StopContextTimeline({
  entries,
}: {
  entries: StopContextEntry[];
}) {
  return (
    <ol className="space-y-3">
      {entries.map((entry, index) => (
        <li key={index} className="relative border-l border-border pl-4">
          <span
            aria-hidden="true"
            className="absolute -left-[3.5px] top-1.5 block h-[7px] w-[7px] rounded-full bg-text-primary"
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-medium text-text-primary">
              {stopReasonLabel(entry.limit)}
            </span>
            <Badge variant={entry.arrived_after ? "outline" : "default"}>
              {entry.arrived_after ? "Arrived after stop" : "Tipping event"}
            </Badge>
          </div>
          <div className="mt-1 space-y-0.5 text-[12px] text-text-secondary">
            <div>
              Scope: {stopScopeLabel(entry.stop_scope)}
              {entry.episode_seq !== null && ` · Episode ${entry.episode_seq}`}
            </div>
            <div>
              {entry.tripped_at
                ? `Limit tripped ${formatDate(entry.tripped_at)}`
                : "No recorded trip time"}
            </div>
            {entry.task_id && (
              <div>
                Task{" "}
                <span className="font-mono text-[11px]">
                  {shortId(entry.task_id)}
                </span>
                {entry.subtask_id && (
                  <>
                    {" · subtask "}
                    <span className="font-mono text-[11px]">
                      {shortId(entry.subtask_id)}
                    </span>
                  </>
                )}
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
