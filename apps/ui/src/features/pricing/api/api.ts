// Real API implementation — one exported function per operation, every call
// wrapped in unwrap() so failures always reject with a typed ApiProblem.

import { meteringApi } from "@/api/client";
import { ApiProblem, unwrap } from "@/api/problem";
import type {
  Book,
  BookIn,
  ListBooksParams,
  ListRatesParams,
  PaginatedBooks,
  PaginatedRates,
  PublishIn,
  TenantMarkup,
  TenantMarkupIn,
} from "./types";

export async function listBooks(params?: ListBooksParams): Promise<PaginatedBooks> {
  return unwrap(
    await meteringApi.GET("/pricing/rate-cards", {
      params: {
        query: {
          card_type: params?.card_type,
          cursor: params?.cursor,
          limit: params?.limit,
        },
      },
    }),
  );
}

export async function createBook(body: BookIn): Promise<Book> {
  return unwrap(await meteringApi.POST("/pricing/rate-cards", { body }));
}

/**
 * The contract has no GET-one-book endpoint; resolve a book by walking the
 * (small) books list. Throws a 404-shaped ApiProblem when absent.
 */
export async function getBook(bookId: string): Promise<Book> {
  let cursor: string | undefined;
  for (let page = 0; page < 10; page++) {
    const result = await listBooks({ cursor, limit: 100 });
    const match = result.data.find((book) => book.id === bookId);
    if (match) return match;
    if (!result.has_more || !result.next_cursor) break;
    cursor = result.next_cursor;
  }
  throw new ApiProblem({
    status: 404,
    code: "not_found",
    title: "Not found",
    detail: "This rate-card book no longer exists.",
  });
}

export async function listRates(
  bookId: string,
  params?: ListRatesParams,
): Promise<PaginatedRates> {
  return unwrap(
    await meteringApi.GET("/pricing/rate-cards/{book_id}/rates", {
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

export async function publishBook(bookId: string, body: PublishIn): Promise<Book> {
  return unwrap(
    await meteringApi.POST("/pricing/rate-cards/{book_id}/publish", {
      params: { path: { book_id: bookId } },
      body,
    }),
  );
}

export async function getTenantMarkup(): Promise<TenantMarkup> {
  return unwrap(await meteringApi.GET("/pricing/markup"));
}

export async function putTenantMarkup(body: TenantMarkupIn): Promise<TenantMarkup> {
  return unwrap(await meteringApi.PUT("/pricing/markup", { body }));
}
