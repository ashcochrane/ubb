// Which kind of posting this is — `usage_event_kind` — and the words for it.
//
// Identity is the registry's (`@/lib/vocabulary`), expression the catalogue's
// (`@/locales`, reached through `@/lib/localisation`) — the split
// `./measurements` makes for the measurement status, one concept over.
// `domain-vocabulary/` names `@/lib/labels` as the console's consumer of the
// value LIST, and that file holds it by reference and nothing else: #425 paid
// `g2-console-usage_event_kind` in the shape slices 3 and 4 established, and
// the legacy adapter is not where a migrated concept's wording lives. The
// words are bound HERE because this feature is the surface that renders a
// posting — the ledger's rows and the receipt — and a surface binds the words
// it renders.
//
// It sits in the events feature rather than in `lib/` for `./measurements`'s
// reason: nothing outside this feature reads a posting's kind. The tasks
// surface renders runs, and a run carries no posting — the contract publishes
// no read of a run's postings, so the one place a charge posting renders as
// itself is here.

//
// Only the name is bound. What a charge posting IS gets said where a reader
// meets the consequences of it — the measurement section's own sentence, and
// the receipt's (`./receipt-subject`) — rather than a third time beside the
// word, so the console explains the state once per place it renders and not
// once per concept that names it.

import { labelMap } from "@/lib/localisation";
import { USAGE_EVENT_KIND_LABEL_KEYS } from "@/lib/vocabulary";

/** The catalogue's name for which kind of posting this is. */
export const usageEventKindLabel = labelMap(USAGE_EVENT_KIND_LABEL_KEYS);
