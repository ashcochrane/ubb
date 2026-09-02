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
import { toastOnError, toastSuccess } from "@/lib/mutations";
import { partialTotalNote, supplierCostTotal } from "@/lib/supplier-cost";
import { taskStatusLabel } from "@/lib/task-status";

import { useCloseTask } from "../api/queries";
import type { CloseTaskResult } from "../api/types";
import { shortId } from "../lib/search";
import { Section } from "./section";

/**
 * What a closed task cost, once it is closed.
 *
 * THE TASK'S OWN COGS, and the one total this console shows for a whole unit of
 * work. It is a FLOOR whenever the task holds events UBB could not cost — and
 * how the ones it COULD cost were derived never enters that: a task mixing
 * calculated and reported events is complete, because nothing is missing from
 * it. The count is the only thing asked.
 */
function ClosedTaskTotals({
  result,
  currency,
}: {
  result: CloseTaskResult;
  currency: string;
}) {
  const stillUnknown = partialTotalNote(result.unresolved_event_count);
  return (
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
            value: supplierCostTotal(
              result.total_provider_cost_micros,
              result,
              currency,
            ),
          },
          ...(stillUnknown
            ? [{ label: "Costs still unknown", value: stillUnknown }]
            : []),
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
  );
}

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
        <ClosedTaskTotals result={result} currency={currency} />
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span title={canWrite ? undefined : "Requires the Write role"}>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmOpen(true)}
              disabled={!canWrite || closeTask.isPending}
            >
              {closeTask.isPending ? "Working…" : "Close as delivered"}
            </Button>
          </span>
          <p className="text-[11px] text-text-muted">
            Declares this task delivered. Any still-running subtasks under it
            are withdrawn rather than marked delivered; late events still land
            and count.
          </p>
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Close this task as delivered?"
        description="This declares the work delivered. Any still-running subtasks under it are withdrawn rather than marked delivered, because nobody declared anything about them. Events that arrive later still land and are billed."
        confirmLabel="Yes, it delivered"
        pending={closeTask.isPending}
        onConfirm={() =>
          // ⚠ THE OUTCOME IS NAMED HERE, at the one place a person actually
          // asserts it (#409). This is the money-moving declaration once a
          // delivery creates a charge, which is why the button and the dialog
          // above both say so rather than reading "Close task" — and why
          // nothing below this line supplies a default.
          closeTask.mutate({ taskId, outcome: "delivered" }, {
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
