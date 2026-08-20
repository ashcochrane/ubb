// Pricing feature — type aliases over the generated contract schemas.
// Every response used by this feature is a fully named component schema, so
// no local "[backend-verified shape]" interfaces are needed here.

import type { MeteringSchemas } from "@/api/types";

export type Book = MeteringSchemas["BookOut"];
export type BookIn = MeteringSchemas["BookIn"];
export type PaginatedBooks = MeteringSchemas["PaginatedBooks"];

export type Rate = MeteringSchemas["RateOut"];
export type RateIn = MeteringSchemas["RateIn"];
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

export type PublishIn = MeteringSchemas["PublishIn"];
export type RateChangeIn = MeteringSchemas["RateChangeIn"];

export type TenantMarkup = MeteringSchemas["TenantMarkupOut"];
export type TenantMarkupIn = MeteringSchemas["TenantMarkupIn"];

export type StatusResponse = MeteringSchemas["StatusResponse"];

/** Query options for the books list. */
export interface ListBooksParams {
  /** "cost" | "price" (open enum) — omit for all books. */
  card_type?: string;
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
