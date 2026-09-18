// What an invoice-line grouping choice means, said where the choice is made
// (#508; slice 7 §6, §11).
//
// ⚠ **THIS IS A BILLING SURFACE READING AN ANALYTICS VOCABULARY, AND THAT IS
// THE WHOLE POINT OF §11.** The axis a tenant's invoice lines are built on is
// one word of the same grouping contract every chart uses — reached, on the
// server, through metering's `queries.py` read contract, which is the only
// channel ADR-001 allows between the two products. A ticket plan scoped by
// analytics route would miss this screen entirely, and it is the one a paying
// customer's invoice is shaped by.

import type { GroupingOption } from "@/lib/grouping-axis";
import { ROLLUP_KIND } from "@/lib/grouping-axis";

/**
 * The stored value that means one line carrying one total.
 *
 * An ABSENCE of grouping rather than an axis meaning "don't": no axis produces
 * a single line, so the way to ask for one is to name none. The empty string
 * is what the contract stores for it, and the PUT is partial, so it has to be
 * sent explicitly to clear a grouping that is already there.
 */
export const SINGLE_LINE = "";
export const SINGLE_LINE_LABEL = "Single line — one total";

/**
 * What changing the rollup an invoice is grouped by actually does.
 *
 * ⚠ **STATED AT THE POINT OF CHANGE, WHICH IS §6's REQUIREMENT AND NOT A
 * COURTESY.** Changing a rollup RECLASSIFIES HISTORY — past work is grouped
 * the new way the next time anything reads it — and that is safe *precisely
 * because rollups touch no money*: no original event, no cost, no Charge, no
 * receipt and no historical monetary amount moves. A tenant reclassifying an
 * event category has to be told both halves, because the first half alone
 * sounds like a restatement of their invoices and the second is what says it
 * is not.
 */
export const ROLLUP_RECLASSIFIES_HISTORY =
  "Changing a rollup reclassifies history: past usage is grouped the new way "
  + "wherever it is read again. It moves no money — no event, cost, charge, "
  + "receipt or past amount changes, only how they are grouped.";

/** Why rollups are the preferred answer here, and not merely an option. */
export const ROLLUPS_ARE_PREFERRED =
  "Rollups are preferred for invoices: fewer lines, each meaning something to "
  + "the customer reading it.";

/**
 * What a tenant should be told about this axis BEFORE they bill on it.
 *
 * ⚠ **THE CONSOLE DECIDES WITH THE SAME FIELD THE SERVER DOES, AND KNOWS LESS
 * THAN IT.** `max_cardinality` is the cap the tenant declared on their own
 * axis; how many distinct values that axis has actually recorded is a count
 * over their postings, which only a query can know — so the server's own
 * warning, computed at configuration time from the real count, is the exact
 * one. What this adds is the half available at the moment of CHOOSING, before
 * anything is stored: this axis is capped, one line per distinct value, and a
 * rollup is the way to fewer.
 *
 * ⚠ **A ROLLUP AND AN AXIS UBB OWNS ANSWER `null`, AND THAT IS NOT AN
 * OMISSION** — they carry no declared cap, so there is no maximum to exceed
 * and nothing honest to say. The row's own `max_cardinality` is what decides,
 * exactly as it does on the server, which keeps the rule in one place rather
 * than in two that can disagree.
 *
 * And it WARNS, never refuses: the cap is a keyspace bound the tenant set on
 * their own axis, not an invariant UBB may decline to bill against.
 */
export function cardinalityWarning(
  option: GroupingOption | undefined,
): string | null {
  if (!option) return null;
  const ceiling = option.max_cardinality;
  if (ceiling === null || ceiling === undefined) return null;
  // ⚠ **THE CAP IS NOT A CEILING ON THE LINE COUNT AND MUST NOT BE WORDED AS
  // ONE.** An earlier draft said the invoice "could run to {ceiling} lines",
  // which reassures exactly where the server warns: `max_cardinality` is a
  // bound the tenant DECLARED, and `invoice_line_cardinality_warning` exists
  // because the values actually recorded can exceed it — its own sentence is
  // "has recorded more than {ceiling} distinct values". So this says the count
  // is unbounded by anything UBB enforces, and names the cap as the number the
  // server measures against.
  return (
    `An invoice grouped by this axis carries one line per distinct value, and `
    + `nothing caps how many that is — you declared ${ceiling} as the most you `
    + `expect, and UBB warns you when this axis has recorded more than that. `
    + `${ROLLUPS_ARE_PREFERRED}`
  );
}

/** Whether the chosen axis is a rollup, so the surface knows what to say. */
export function isRollup(option: GroupingOption | undefined): boolean {
  return option?.kind === ROLLUP_KIND;
}
