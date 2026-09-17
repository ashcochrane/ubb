// One axis of the grouping contract, rendered with its kind visible (#506).
//
// §6's whole ruling is that the difference between a FIELD and a ROLLUP stays
// visible to the caller: a field is a column and a rollup is a join, with
// different cardinality and cost, and an untyped list hides that behind
// identical-looking strings. A picker that showed one flat list of names would
// undo the ruling at the last inch, so the kind renders beside every axis.
//
// ⚠ **THE OPEN-SET RULE, THROUGH THE ONE HELPER AND NOT A SECOND COPY.** Two
// things on a row can be a value this console has no word for — the KIND, and
// the ROLLUP an axis names — because ADR-0003 keeps every categorical field an
// open string and a server may answer a value newer than this build. Both go
// through `OpenSetValue`, which renders the token itself, marked, and never
// title-cased into English UBB did not author. The AXIS NAME takes the same
// treatment for the same reason, via the tenant-defined lookup: a name nothing
// has words for is shown exactly as the server sent it.
//
// The tenant's OWN axis is the one case that is not an open-set question at
// all. Its word arrived on the row, the tenant wrote it, and it renders
// verbatim — unmarked, because there is nothing unrecognised about it.

import { OpenSetValue } from "@/components/shared/open-set-value";
import { axisName, type GroupingOption } from "@/lib/grouping-axis";
import { NO_DECLARED_VALUES } from "@/lib/localisation";
import { ANALYTICS_GROUPING_KIND_LABEL_KEYS } from "@/lib/vocabulary";

/** The axis's own name: words where anyone has them, the marked token where nobody does. */
export function GroupingAxisName({ option }: { option: GroupingOption }) {
  const name = axisName(option);
  if (name.kind === "unworded") {
    // `NO_DECLARED_VALUES` resolves every value `unfamiliar`, which is exactly
    // true here: no concept declares this axis's name, so the helper's own
    // branch is the honest one rather than a special case beside it.
    return <OpenSetValue labelKeys={NO_DECLARED_VALUES} value={name.text} />;
  }
  return <span data-axis={name.kind}>{name.text}</span>;
}

/** Whether this axis is a column on the event or a join to a rollup UBB owns. */
export function GroupingAxisKind({ option }: { option: GroupingOption }) {
  return (
    <span className="text-[11px] text-text-muted">
      <OpenSetValue
        labelKeys={ANALYTICS_GROUPING_KIND_LABEL_KEYS}
        value={option.kind}
      />
    </span>
  );
}

/** One picker row: the axis, then what kind of thing it is. */
export function GroupingAxisLabel({ option }: { option: GroupingOption }) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <GroupingAxisName option={option} />
      <GroupingAxisKind option={option} />
    </span>
  );
}
