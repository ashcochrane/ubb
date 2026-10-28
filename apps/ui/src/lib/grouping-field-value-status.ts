// What an economic row says about its value on a grouping axis (#550).
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/products` pattern. Declared in R10-W4 (slice 8), which deleted the
// hand-written map in `@/lib/labels` this replaces; that map fell back to the
// humaniser, which ADR-0008 §4.3 calls a defect. The registry names this file
// as the console's consumer of the concept(s) below.
//
// `not_recorded` and `not_applicable` both leave an axis without a value, and
// they read differently on purpose: the first is a gap in what was reported,
// which has a remedy, the second is a kind of row that never carries one. It
// sits in `lib/` because the dashboard and the events feature both draw a
// grouped breakdown.

import { labelMap } from "@/lib/localisation";
import {
  GROUPING_FIELD_VALUE_STATUS_LABEL_KEYS,
  type GroupingFieldValueStatus,
} from "@/lib/vocabulary";

/** The catalogue's words for why a row has, or lacks, a value on an axis. */
export const groupingFieldValueStatusLabel = labelMap(
  GROUPING_FIELD_VALUE_STATUS_LABEL_KEYS,
);

/**
 * What a grouped row is called by its axis: the value itself where one was
 * recorded, and otherwise the catalogue's word for WHICH absence it is. The
 * report this replaced put both absences under one `(unattributed)` heading,
 * which is the conflation #550 exists to end — only one of them has a remedy.
 * A tenant's value renders exactly as they recorded it.
 */
export function axisHeading(
  value: string | null | undefined,
  status: GroupingFieldValueStatus | null | undefined,
): string {
  if (value !== null && value !== undefined) return value;
  return groupingFieldValueStatusLabel(status);
}
