// The revenue view a surface's figures were stated under, said beside them
// (#548; W5 owner ruling 15).
//
// ⚠ **EVERY SURFACE THAT RENDERS A REVENUE, OR A MARGIN TAKEN FROM ONE, SAYS
// WHICH VIEW IT IS — AND SAYS IT FROM THE ANSWER.** A revenue may hold an
// amount the tenant supplied, which `recorded` places whole on the day its
// period opens and `recognised` spreads across the period it covers (slice 7
// §5). The two are different figures over the same records, so a figure with
// no basis beside it is one its reader cannot interpret. The `basis` handed in
// is the one the RESPONSE states; a console constant standing in for it would
// be a claim the server never made, which is the defect this note exists to
// end.
//
// ⚠ ONE NOTE PER SECTION, AND ONLY WHERE THE SECTION IS ONE ANSWER. A page that
// composes several answers renders one of these beside each, never one
// umbrella note: two answers may state two bases, and the customer overview
// does exactly that (its business rollup is always `recognised`).
//
// It lives here rather than in a feature because four features render it,
// and `data-revenue-basis` carries the server's word on the node so a test
// asserts WHICH view the surface claims rather than matching a sentence.

import { revenueBasisNote } from "@/lib/supplied-revenue";
import { cn } from "@/lib/utils";
import type { RevenueBasis } from "@/lib/vocabulary";

export function RevenueBasisNote({
  basis,
  className,
}: {
  /** The basis the response states — never a value the console chose. */
  basis: RevenueBasis;
  className?: string;
}) {
  return (
    <p data-revenue-basis={basis} className={cn("text-[11px] text-text-muted", className)}>
      {revenueBasisNote(basis)}
    </p>
  );
}
