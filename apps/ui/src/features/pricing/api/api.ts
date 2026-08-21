// Real API implementation — one exported function per operation, every call
// wrapped in unwrap() so failures always reject with a typed ApiProblem.

import { meteringApi } from "@/api/client";
import { ApiProblem, unwrap } from "@/api/problem";
import type {
  AnyBook,
  CostBook,
  CostBookIn,
  ListBooksParams,
  ListRatesParams,
  PaginatedCostBooks,
  PaginatedPricingBooks,
  PaginatedRates,
  PricingBook,
  PricingBookIn,
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

export async function listRates(
  bookId: string,
  params?: ListRatesParams,
): Promise<PaginatedRates> {
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

// ⚠ NO `publishBook` (#368). The immediate reprice route it called is deleted
// with the last of the retired audit action names it wrote — every change to a
// book is a declared change on a publish now, read as a diff before it is
// committed to. This console cannot change what is in a book until #372
// rebuilds the feature around books, rules and publishes; the gap is visible
// rather than hidden, which is the same trade #367 made when the add-a-rule
// dialog went.

// ⚠ NO TENANT-MARKUP READ OR WRITE (#369). The record those two routes read
// and wrote is deleted, along with the routes, their two component schemas and
// the two audit action names they carried. What replaced it is the tenant's
// DECLARED default markup rung, on its own path — and this console does not
// reach it yet: #372 rebuilds this feature around books, rules and publishes,
// and the rung belongs on that page beside them. The gap is visible rather
// than hidden, which is the same trade the note above makes.
