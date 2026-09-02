// The lifecycle words for a unit of work, and the console's own copy beside
// them (#424, spec §26).
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation`. This module
// is where the two meet for `task_status` — the `@/lib/products` shape — plus
// the one thing neither of them may hold: what each state means for the
// person reading it.
//
// ⚠ IT SITS IN `lib/`, WHICH IS A DELIBERATE DEPARTURE FROM THE LETTER OF
// SPEC §26. §26 binds the lifecycle words "at the surface that renders them —
// the tasks feature". Two features render a lifecycle state: the runs surface
// is `features/tasks`, and the receipt's task panel — which shows a close's
// answer — is `features/events`. The console's imports only flow down, so a
// binding inside either feature would have to be written twice, and two
// bindings of one concept is the drift the localisation layer exists to
// abolish. That is the rule `@/lib/customer-price` states for the pricing
// method (#372), applied to the second concept it turned out to cover; the
// tasks feature is still the first surface to render every one of the six.
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
 *
 * ⚠ THE `expired` SENTENCE CARRIES A RULE: an expired run is not a failure
 * (#187 §7, #140 §11). Expiry means nobody declared an ending, and it can
 * strike live work in the middle of a long atomic call — an accepted
 * consequence of having no keepalive, acceptable only while it stays visible
 * for what it is. A cancelled run is a withdrawal, not a verdict, and a killed
 * run is UBB's own spend stop, which says something about the ceiling and
 * nothing about whether the work was going well. How each is DRAWN follows
 * from this in `features/tasks/components/run-status-badge.tsx`.
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
