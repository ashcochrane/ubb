// What the pricing feature says and sends about an agreed price (#553): the
// console copy beside a metering-only workspace's prices, and the one place a
// typed agreed price becomes the change body the publish act takes.

import type { BookAgreedPriceChangeIn } from "../api/types";
import { toMicros } from "./pricing-math";
import type { ChangeKind } from "./rules";
import type { AgreedPriceFormValues } from "./schemas";

/**
 * What a Pricing Book is to a workspace that meters without billing through
 * UBB (#553 story 17). The book is theirs — billing mode does not decide
 * whether UBB may know a customer's agreed price — so its prices are recorded
 * for their own margin reporting and collected from nobody. The day billing is
 * enabled that changes, and the sentence says so beside the prices, before
 * that day rather than on it.
 */
export const METERING_ONLY_PRICES =
  "This workspace meters without billing through UBB, so the prices in this book are recorded for your own margin reporting and no customer is charged them. If you enable billing later, UBB starts collecting them from your customers — the agreed prices here included.";

/**
 * One typed agreed price as the change the publish act takes.
 *
 * ⚠ **A RETIREMENT STATES NO AMOUNT AT ALL** — it opens no line, so an amount
 * beside it would be a number nobody will ever read, and the API refuses one.
 */
export function agreedPriceChange(
  kind: ChangeKind,
  values: AgreedPriceFormValues,
): BookAgreedPriceChangeIn {
  const task_type = values.task_type.trim();
  return kind === "retire"
    ? { line: "agreed_price", kind, task_type }
    : { line: "agreed_price", kind, task_type, agreed_price_micros: toMicros(values.amount) };
}
