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
 * Taken off the READ schema rather than declared here. It is a closed registry
 * concept, so the contract publishes a real `enum` for it and the generated
 * types carry that as a union; a hand-written copy would be one the day a value
 * moves, and this feature both sends and renders the value.
 */
export type RateStructure = Rate["rate_structure"];

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
