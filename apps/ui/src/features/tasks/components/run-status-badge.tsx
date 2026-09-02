import { Badge } from "@/components/ui/badge";
import {
  TASK_STATUS_EXPLANATIONS,
  TASK_STATUS_TONES,
  taskStatusLabel,
  type TaskStatusTone,
} from "@/lib/task-status";
import type { TaskStatus } from "@/lib/vocabulary";

/**
 * How each tone is drawn. Red is reserved for a failure (`apps/ui/CLAUDE.md`),
 * and a failure is `failed` alone: an expired run, a cancelled one and one UBB
 * stopped are each drawn as their own thing, never as the caller's verdict.
 */
const VARIANT_BY_TONE = {
  live: "outline",
  delivered: "secondary",
  failure: "destructive",
  withdrawn: "outline",
  stopped: "secondary",
  expired: "outline",
} as const satisfies Record<TaskStatusTone, "outline" | "secondary" | "destructive">;

/**
 * A run's lifecycle state, in the catalogue's words, drawn by its tone.
 *
 * `data-tone` is the tone itself, so a test can assert what a state was drawn
 * AS rather than matching a class name — and so "an expired run is not
 * rendered as a failure" is a claim about an attribute, not about prose.
 */
export function RunStatusBadge({ status }: { status: TaskStatus }) {
  const tone = TASK_STATUS_TONES[status];
  return (
    <Badge variant={VARIANT_BY_TONE[tone]} data-tone={tone} title={TASK_STATUS_EXPLANATIONS[status]}>
      {taskStatusLabel(status)}
    </Badge>
  );
}
