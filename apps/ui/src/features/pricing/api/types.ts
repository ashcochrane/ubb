// Pricing feature — type aliases over the generated contract schemas.
// Every response used by this feature is a fully named component schema, so
// no local "[backend-verified shape]" interfaces are needed here.

import type { MeteringSchemas } from "@/api/types";

// ⚠ THE CONTAINER IS TWO ENTITIES (#368). A Pricing Book is a catalogue of
// what this tenant charges and names neither a supplier nor a currency; a cost
// book records what one supplier charges and names both. They are separate
// component schemas because they are separate things, and a `Book` alias over
// either would put back exactly the conflation the split removed.
export type PricingBook = MeteringSchemas["PricingBookOut"];
export type PricingBookIn = MeteringSchemas["PricingBookIn"];
export type PaginatedPricingBooks = MeteringSchemas["PaginatedPricingBooks"];

export type CostBook = MeteringSchemas["CostBookOut"];
export type CostBookIn = MeteringSchemas["CostBookIn"];
export type PaginatedCostBooks = MeteringSchemas["PaginatedCostBooks"];

/** Either kind, for the screens whose subject is a book's CONTENTS. */
export type AnyBook = PricingBook | CostBook;

/** Whether a book of either kind records supplier costs. */
export function isCostBook(book: AnyBook): book is CostBook {
  return "provider_key" in book;
}

export type Rate = MeteringSchemas["RateOut"];
// ⚠ NO `RateIn` (#367) AND NO `RateChangeIn` (#368). Both bodies that wrote a
// rule immediately are deleted from the contract with their routes: adding,
// repricing and retiring a rule are declared changes on a publish now. The
// declaring body is `BookChangeIn`, and the feature that speaks it arrives
// with #372 — until then this console reads books and rules and declares
// books, and cannot change what is in one.
export type PaginatedRates = MeteringSchemas["PaginatedRates"];

/**
 * Which arithmetic a rule runs — per unit of quantity, or once regardless.
 *
 * ⚠ RE-EXPORTED FROM THE REGISTRY RATHER THAN DERIVED FROM THE SCHEMA. The
 * first draft wrote `Rate["rate_structure"]`, which is the same two members and
 * is still the wrong source: `@/lib/vocabulary` is this console's declared
 * consumer of the registry (`docs/conventions/coding-standards.md` §Vocabulary),
 * and a type read off the generated contract makes the CONTRACT the authority
 * on a value set the registry owns. It is re-exported here rather than imported
 * at each use so this feature has one name for the concept, which is what the
 * other aliases in this file are for.
 */
export type { RateStructure } from "@/lib/vocabulary";

export type TenantMarkup = MeteringSchemas["TenantMarkupOut"];
export type TenantMarkupIn = MeteringSchemas["TenantMarkupIn"];

export type StatusResponse = MeteringSchemas["StatusResponse"];

/** Query options for either books list. */
export interface ListBooksParams {
  cursor?: string;
  limit?: number;
}

/** Query options for a book's rates list. */
export interface ListRatesParams {
  /** Include superseded/retired versions (rows carrying a valid_to). */
  include_history?: boolean;
  /** Point-in-time view (ISO datetime). Takes precedence over include_history. */
  as_of?: string;
  cursor?: string;
  limit?: number;
}
