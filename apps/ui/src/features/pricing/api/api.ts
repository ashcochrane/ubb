// Real API implementation — one exported function per operation, every call
// wrapped in unwrap() so failures always reject with a typed ApiProblem.

import { meteringApi } from "@/api/client";
import { ApiProblem, unwrap } from "@/api/problem";
import type {
  AnyBook,
  BookPublish,
  BookPublishIn,
  CostBook,
  CostBookIn,
  CustomerOverrideIn,
  GroupingFieldDef,
  GroupingFieldRegistry,
  InheritedRule,
  InheritedRuleParams,
  ListBooksParams,
  ListRulesParams,
  PaginatedBookPublishes,
  PaginatedCostBooks,
  PaginatedPricingBooks,
  PaginatedRules,
  PricingBook,
  PricingBookIn,
  StatusResponse,
  TenantDefaultMarkup,
  TenantDefaultMarkupIn,
} from "./types";

export async function listPricingBooks(
  params?: ListBooksParams,
): Promise<PaginatedPricingBooks> {
  return unwrap(
    await meteringApi.GET("/pricing/pricing-books", {
      params: { query: { cursor: params?.cursor, limit: params?.limit } },
    }),
  );
}

export async function listCostBooks(
  params?: ListBooksParams,
): Promise<PaginatedCostBooks> {
  return unwrap(
    await meteringApi.GET("/pricing/cost-books", {
      params: { query: { cursor: params?.cursor, limit: params?.limit } },
    }),
  );
}

export async function declarePricingBook(
  body: PricingBookIn,
): Promise<PricingBook> {
  return unwrap(await meteringApi.POST("/pricing/pricing-books", { body }));
}

export async function declareCostBook(body: CostBookIn): Promise<CostBook> {
  return unwrap(await meteringApi.POST("/pricing/cost-books", { body }));
}

/**
 * The contract has no GET-one-book endpoint; resolve a book by walking the
 * (small) lists. BOTH of them, because a book id names one book of one of two
 * kinds and the screen that asks does not know which (#368). Throws a
 * 404-shaped ApiProblem when absent.
 */
export async function getBook(bookId: string): Promise<AnyBook> {
  for (const list of [listPricingBooks, listCostBooks]) {
    let cursor: string | undefined;
    for (let page = 0; page < 10; page++) {
      const result = await list({ cursor, limit: 100 });
      const match = (result.data as AnyBook[]).find(
        (book) => book.id === bookId,
      );
      if (match) return match;
      if (!result.has_more || !result.next_cursor) break;
      cursor = result.next_cursor;
    }
  }
  throw new ApiProblem({
    status: 404,
    code: "not_found",
    title: "Not found",
    detail: "This book no longer exists.",
  });
}

export async function listRules(
  bookId: string,
  params?: ListRulesParams,
): Promise<PaginatedRules> {
  return unwrap(
    await meteringApi.GET("/pricing/books/{book_id}/rates", {
      params: {
        path: { book_id: bookId },
        query: {
          include_history: params?.include_history,
          as_of: params?.as_of,
          cursor: params?.cursor,
          limit: params?.limit,
        },
      },
    }),
  );
}

// --- Publishes: the one way a book changes ----------------------------------
//
// ⚠ **FOUR CALLS AND NO FIFTH.** There is no route that changes a rule
// immediately: the three the console used to drive — add a rule, retire one,
// reprice a set — were deleted with the acts they recorded (#367, #368), and
// what replaced them is one act declared as a draft and then published. So the
// console declares (a draft, with its diff), reads (the drafts pending on a
// book), publishes, and discards. A caller that wanted "just change this one
// rule" composes a one-change draft and publishes it, which is what the rule
// editor does — the convenience is in the UI and the record is still one
// publish.

/**
 * The changes PENDING on this book — the drafts, newest first, each with its
 * diff.
 *
 * ⚠ **DRAFTS ONLY, AND THAT IS THE ROUTE'S OWN ANSWER RATHER THAN A FILTER
 * THIS CONSOLE APPLIES.** *What is about to happen to my prices* is the
 * question; a published record is history and the governance ledger is where
 * history is read. The book's page shows both, and the second comes from the
 * audit trail rather than from here.
 */
export async function listBookPublishes(
  bookId: string,
  params?: { cursor?: string; limit?: number },
): Promise<PaginatedBookPublishes> {
  return unwrap(
    await meteringApi.GET("/pricing/books/{book_id}/publishes", {
      params: {
        path: { book_id: bookId },
        query: { cursor: params?.cursor, limit: params?.limit },
      },
    }),
  );
}

// ⚠ NO `getBookPublish`. The route exists — one change, with its diff — and no
// screen asks it: the list already answers with every pending draft's diff, so
// fetching one by id would be a second way to get what the console already has.
// A wrapper with no caller is a dead export the next reader has to classify.

/**
 * Declare a change to a book: the intended changes, and nothing written.
 *
 * The response carries the diff — what the book will look like afterwards — so
 * a tenant decides against the OUTCOME rather than against their own request.
 */
export async function declareBookPublish(
  bookId: string,
  body: BookPublishIn,
): Promise<BookPublish> {
  return unwrap(
    await meteringApi.POST("/pricing/books/{book_id}/publishes", {
      params: { path: { book_id: bookId } },
      body,
    }),
  );
}

/** Publish a declared change: close each superseded rule, open its replacement. */
export async function publishBookPublish(
  bookId: string,
  publishId: string,
): Promise<BookPublish> {
  return unwrap(
    await meteringApi.POST(
      "/pricing/books/{book_id}/publishes/{publish_id}/publish",
      { params: { path: { book_id: bookId, publish_id: publishId } } },
    ),
  );
}

/** Discard a draft, leaving the book exactly as it stood. */
export async function discardBookPublish(
  bookId: string,
  publishId: string,
): Promise<StatusResponse> {
  return unwrap(
    await meteringApi.DELETE("/pricing/books/{book_id}/publishes/{publish_id}", {
      params: { path: { book_id: bookId, publish_id: publishId } },
    }),
  );
}

// --- One customer's own rules -----------------------------------------------

/**
 * What this customer is charged for a rule where they have no override.
 *
 * ⚠ **THE STARTING POINT FOR WRITING ONE, WHICH IS WHY THE CONSOLE ASKS BEFORE
 * IT OFFERS THE EDITOR.** It is the same ladder one rung shorter, so the method
 * and the current value shown cannot drift from what is about to be replaced —
 * and `rule` is null where nothing is inherited, which is an ordinary state
 * rather than an error.
 *
 * Each grouping field goes on the wire as one `grouping_field=key=value`
 * parameter, repeated. The map is the console's shape because a map is what a
 * rule pins; the flattening is this function's job and nobody else's.
 */
export async function getInheritedRule(
  customerId: string,
  params: InheritedRuleParams,
): Promise<InheritedRule> {
  return unwrap(
    await meteringApi.GET("/pricing/customers/{customer_id}/inherited-rule", {
      params: {
        path: { customer_id: customerId },
        query: {
          measurement_key: params.measurement_key,
          provider: params.provider,
          event_type: params.event_type,
          task_type: params.task_type,
          subtask_type: params.subtask_type,
          grouping_field: Object.entries(params.grouping_fields ?? {}).map(
            ([key, value]) => `${key}=${value}`,
          ),
          as_of: params.as_of,
        },
      },
    }),
  );
}

/**
 * Declare one customer's own pricing rule, as a draft on their own book.
 *
 * ⚠ **THIS WRITES NO RULE, AND THE RESPONSE IS A PUBLISH FOR THAT REASON.**
 * The deal comes into force when that draft is published through the book's own
 * route — there is no immediate-effect path to an override and no second
 * mutation surface for one.
 */
export async function declareCustomerOverride(
  customerId: string,
  body: CustomerOverrideIn,
): Promise<BookPublish> {
  return unwrap(
    await meteringApi.POST("/pricing/customers/{customer_id}/overrides", {
      params: { path: { customer_id: customerId } },
      body,
    }),
  );
}

// ⚠ NO `withdrawCustomerOverride`, AND THE ACT IS STILL REACHABLE. Ending a
// customer's own deal declares a draft that RETIRES the rule, and a customer's
// own book is a Pricing Book like any other — it is in the books list, its page
// declares changes, and "retire a rule" is one of the three a change may be. So
// the console reaches this act through the surface every other book uses,
// rather than through a second path that would have to agree with the first
// forever.

// --- The markup rung --------------------------------------------------------

/** What the tenant has declared, or null if they have declared nothing. */
export async function getTenantDefaultMarkup(): Promise<TenantDefaultMarkup> {
  return unwrap(await meteringApi.GET("/pricing/default-markup"));
}

/** Declare the tenant's default markup rung, or re-declare it. */
export async function declareTenantDefaultMarkup(
  body: TenantDefaultMarkupIn,
): Promise<TenantDefaultMarkup> {
  return unwrap(await meteringApi.PUT("/pricing/default-markup", { body }));
}

/** Withdraw the rung, leaving the tenant with none — NOT the same as zero. */
export async function withdrawTenantDefaultMarkup(): Promise<StatusResponse> {
  return unwrap(await meteringApi.DELETE("/pricing/default-markup"));
}

// --- The tenant's declared grouping vocabulary ------------------------------

/**
 * This tenant's declared Grouping Fields, which is how the rule editor knows
 * which slots exist to pin (#366 ruling 15).
 *
 * It lives in the pricing feature's API module rather than being imported from
 * another feature because the console's imports only flow down: two features
 * reading one route is two thin wrappers, and a shared one would have to sit in
 * `lib/`, where an API call does not belong.
 *
 * ⚠ **IT RETURNS THE LIST AND NOT THE ENVELOPE, AND THAT IS THE FORBIDDEN-TERM
 * SWEEP'S DOING AS MUCH AS TASTE.** The wire wraps the list in a property whose
 * name is a term slice 7 retires, and that term's console ledger entry counts
 * the files holding it — a count that is a ceiling on SPREAD as well as a
 * floor, so a feature reading that key in four components would put the entry
 * over and fail the gate on a debt it does not own. Unwrapping here is Phase
 * B's second technique: the word sits ONCE, in the place whose job is to turn a
 * wire envelope into what the console actually wants, and every caller says
 * what it means. It is also the better shape on its own terms — no consumer of
 * this function has any use for the envelope — which is why it is not a
 * workaround.
 */
export async function listGroupingFields(): Promise<GroupingFieldDef[]> {
  const registry: GroupingFieldRegistry = unwrap(
    await meteringApi.GET("/grouping-fields"),
  );
  return registry.dimensions;
}
