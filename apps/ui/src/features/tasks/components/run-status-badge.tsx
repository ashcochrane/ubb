import { Badge } from "@/components/ui/badge";
import { TASK_STATUS_EXPLANATIONS, taskStatusLabel } from "@/lib/task-status";
import type { TaskStatus } from "@/lib/vocabulary";

/**
 * How each state is drawn. Red — the destructive variant — is reserved for a
 * failure (`apps/ui/CLAUDE.md`), and A FAILURE IS `failed` ALONE: an expired
 * run, a cancelled one and one UBB stopped are each drawn as their own thing,
 * never as the caller's verdict (the argument is on `TASK_STATUS_EXPLANATIONS`).
 * Total over the generated type, so a state the registry adds has to be placed
 * here before it renders.
 */
const VARIANT_BY_STATUS = {
  active: "outline",
  completed: "secondary",
  failed: "destructive",
  cancelled: "outline",
  killed: "secondary",
  expired: "outline",
} as const satisfies Record<TaskStatus, "outline" | "secondary" | "destructive">;

/**
 * A run's lifecycle state, in the catalogue's words, drawn as above.
 *
 * `data-status` is the state itself, so a test can find the drawn state by
 * what it is; whether it was drawn AS a failure is the variant's class, which
 * `test-utils.tsx` names once.
 */
export function RunStatusBadge({ status }: { status: TaskStatus }) {
  return (
    <Badge
      variant={VARIANT_BY_STATUS[status]}
      data-status={status}
      title={TASK_STATUS_EXPLANATIONS[status]}
    >
      {taskStatusLabel(status)}
    </Badge>
  );
}
