// What one wallet movement was: the registry's words for a transaction type.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/products` pattern. Declared in R10-W4 (slice 8), which deleted the
// hand-written map in `@/lib/labels` this replaces; that map fell back to the
// humaniser, which ADR-0008 §4.3 calls a defect. The registry names this file
// as the console's consumer of the concept(s) below.
//
// The types are lowercase since R10-W4 (ruling 7): the ledger spelled them in
// upper case until then, outside the registry's token rule, and no other
// spelling is served afterwards.

import { labelMap } from "@/lib/localisation";
import { WALLET_TRANSACTION_TYPE_LABEL_KEYS } from "@/lib/vocabulary";

/** The catalogue's words for a wallet transaction type. */
export const transactionTypeLabel = labelMap(WALLET_TRANSACTION_TYPE_LABEL_KEYS);
