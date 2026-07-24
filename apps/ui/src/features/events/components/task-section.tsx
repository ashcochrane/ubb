// The receipt's task panel: shows the attributed task and offers "Close
// task" (Write floor). After closing, the returned status + rolled-up totals
// are shown inline.

import { useState } from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { CopyButton } from "@/components/shared/copy-button";
import { DetailList } from "@/components/shared/detail-list";
import { Button } from "@/components/ui/button";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatEventCount, formatMicros } from "@/lib/format";
import { taskStatusLabel } from "@/lib/labels";
import { toastOnError, toastSuccess } from "@/lib/mutations";

import { useCloseTask } from "../api/queries";
import { shortId } from "../lib/search";
import { Section } from "./section";

export function TaskSection({ taskId }: { taskId: string }) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const canWrite = useHasRole("write");
  const currency = useTenantCurrency();
  const closeTask = useCloseTask();
  const result = closeTask.data;

  return (
    <Section title="Task" description="This event is attributed to a task.">
      <div className="flex items-center gap-1.5">
        <span className="break-all font-mono text-[12px] text-text-primary">
          {taskId}
        </span>
        <CopyButton value={taskId} label="Copy task ID" />
      </div>

      {result ? (
        <div className="mt-3 rounded-md bg-bg-subtle p-3">
          <p className="text-[13px] font-medium text-text-primary">
            Task closed — {taskStatusLabel(result.status)}
          </p>
          <DetailList
            className="mt-1"
            items={[
              {
                label: "Events",
                value: formatEventCount(result.event_count),
              },
              {
                label: "Total billed",
                value: formatMicros(result.total_billed_cost_micros, currency),
              },
              {
                label: "Total provider cost",
                value: formatMicros(
                  result.total_provider_cost_micros,
                  currency,
                ),
              },
              ...(result.parent_task_id
                ? [
                    {
                      label: "Parent task",
                      value: shortId(result.parent_task_id),
                      mono: true,
                    },
                  ]
                : []),
            ]}
          />
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span title={canWrite ? undefined : "Requires the Write role"}>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmOpen(true)}
              disabled={!canWrite || closeTask.isPending}
            >
              {closeTask.isPending ? "Working…" : "Close task"}
            </Button>
          </span>
          <p className="text-[11px] text-text-muted">
            Marks the job finished. A parent's active subtasks complete with
            it; late events still land and count.
          </p>
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Close this task?"
        description="Closing marks the task completed and completes any active subtasks under it. Events that arrive later still land and are billed."
        confirmLabel="Yes, close it"
        pending={closeTask.isPending}
        onConfirm={() =>
          closeTask.mutate(taskId, {
            onSuccess: (res) => {
              setConfirmOpen(false);
              toastSuccess(
                "Task closed",
                `${taskStatusLabel(res.status)} — ${formatEventCount(res.event_count)} events.`,
              );
            },
            onError: toastOnError("Couldn't close the task"),
          })
        }
      />
    </Section>
  );
}
