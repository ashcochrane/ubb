import { useState, type ReactElement } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import {
  DetailGrid,
  DetailRow,
  ErrorInline,
} from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { formatMicros, formatEventCount } from "@/lib/format";
import { useCloseTask } from "../api/queries";

/**
 * Close a task by ID and surface the returned settlement summary (status,
 * total billed vs provider cost, event count).
 */
export function CloseTaskDialog({ trigger }: { trigger: ReactElement }) {
  const [open, setOpen] = useState(false);
  const [taskId, setTaskId] = useState("");
  const close = useCloseTask();
  const result = close.data;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!taskId.trim()) return;
    close.mutate(taskId.trim());
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setTaskId("");
      close.reset();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger render={trigger} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Close task</DialogTitle>
          <DialogDescription>
            Finalize a task and see its settled totals. This closes the task for
            further usage.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <FormField label="Task ID">
            {(id) => (
              <Input
                id={id}
                value={taskId}
                onChange={(e) => setTaskId(e.target.value)}
                placeholder="task_…"
              />
            )}
          </FormField>
          {close.isError && (
            <ErrorInline error={close.error} title="Couldn't close task" />
          )}
          {result && (
            <div className="rounded-lg bg-muted p-3">
              <DetailGrid>
                <DetailRow label="Status">
                  <StatusBadge value={result.status} />
                </DetailRow>
                <DetailRow label="Events">
                  {formatEventCount(result.event_count)}
                </DetailRow>
                <DetailRow label="Billed (customer charge)">
                  {formatMicros(result.total_billed_cost_micros)}
                </DetailRow>
                <DetailRow label="Provider cost">
                  {formatMicros(result.total_provider_cost_micros)}
                </DetailRow>
              </DetailGrid>
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
            <Button type="submit" disabled={close.isPending || !taskId.trim()}>
              {close.isPending ? "Closing…" : "Close task"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
