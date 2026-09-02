// The lifecycle words for a unit of work, and the console's own copy beside
// them (#424, spec §26).
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation`. This module
// is where the two meet for `task_status` — the `@/lib/products` shape — plus
// the two things neither of them may hold: what each state means for the
// person reading it, and which one of them is a failure.
//
// IT SITS IN `lib/` RATHER THAN IN THE TASKS FEATURE because two features
// render a lifecycle state and they cannot share one: the runs surface is
// `features/tasks`, and the receipt's task panel — which shows a close's
// answer — is `features/events`. The console's imports only flow down, so a
// binding inside either feature would have to be written twice. That is the
// rule `@/lib/customer-price` states for the pricing method (#372), applied to
// the second concept it turned out to cover.
//
// THIS IS THE PAYMENT OF `g2-console-task_status` AND `g6-map-task-status-label`
// TOGETHER, in the shape slices 3 and 4 established (spec §26): the four-state
// hand-written map in `@/lib/labels` is deleted; that file holds the value
// list by reference, because the registry names it the console's consumer;
// the words have been in the catalogue under `task_status.*` — all six —
// since slice 0; and `taskStatusLabel` below is the binding. A value list and
// the words for it cannot honestly move apart, which is why the two entries
// die in one commit.

import { labelMap } from "@/lib/localisation";
import { TASK_STATUS_LABEL_KEYS, type TaskStatus } from "@/lib/vocabulary";

/** The catalogue's words for a lifecycle state; the raw token for an unfamiliar one. */
export const taskStatusLabel = labelMap(TASK_STATUS_LABEL_KEYS);

/**
 * What each state means for the person reading a run — console-owned copy
 * (ADR-0008 §4.5), total over the generated type so a state the registry adds
 * and this has no sentence for fails `tsc` rather than rendering nothing.
 */
export const TASK_STATUS_EXPLANATIONS = {
  active: "Still running. Usage reported under it is still landing and counting.",
  completed:
    "Delivered: the caller declared the work done. For a kind of work sold at one agreed price, this is what makes that price owed.",
  failed: "The caller declared the work did not deliver, and said why.",
  cancelled:
    "Withdrawn without a verdict either way — by the caller, or because the work containing it was closed first.",
  killed:
    "UBB stopped it on a spend signal. Usage that arrives late still lands and counts.",
  expired:
    "Nobody told UBB how this ended, so UBB closed it when its window ran out. Not a failure: expiry can strike live work that reports nothing for a while, and it is recorded as its own state so it is never counted as one.",
} as const satisfies Record<TaskStatus, string>;

/**
 * How a state reads at a glance.
 *
 * ⚠ `failure` IS `failed` AND NOTHING ELSE. An expired run is not a failure
 * (#187 §7, #140 §11): expiry means nobody declared an ending, and it can
 * strike live work in the middle of a long atomic call — an accepted
 * consequence of having no keepalive, acceptable only while it stays visible
 * for what it is. A cancelled run is a withdrawal, not a verdict. A killed run
 * is UBB's own spend stop, which says something about the ceiling and nothing
 * about whether the work was going well. Grouping, counting or colouring any
 * of the three as a failure would make a spend signal or a missing declaration
 * read as the caller's verdict, which none of them is.
 */
export type TaskStatusTone =
  | "live"
  | "delivered"
  | "failure"
  | "withdrawn"
  | "stopped"
  | "expired";

export const TASK_STATUS_TONES = {
  active: "live",
  completed: "delivered",
  failed: "failure",
  cancelled: "withdrawn",
  killed: "stopped",
  expired: "expired",
} as const satisfies Record<TaskStatus, TaskStatusTone>;
