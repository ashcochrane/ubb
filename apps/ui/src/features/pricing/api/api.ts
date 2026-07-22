import { meteringApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type { CursorPage } from "@/lib/use-cursor-list";
import type {
  Book,
  BookInput,
  Rate,
  RateInput,
  PublishInput,
  TenantMarkup,
  TenantMarkupInput,
} from "./types";

export function listBooks(params?: {
  card_type?: string;
  cursor?: string;
  limit?: number;
}): Promise<CursorPage<Book>> {
  return meteringApi
    .GET("/pricing/rate-cards", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load rate cards"));
}

export function createBook(body: BookInput): Promise<Book> {
  return meteringApi
    .POST("/pricing/rate-cards", { body })
    .then((r) => requireData(r, "Failed to create rate card"));
}

export function listRates(
  bookId: string,
  params?: {
    include_history?: boolean;
    as_of?: string;
    cursor?: string;
    limit?: number;
  },
): Promise<CursorPage<Rate>> {
  return meteringApi
    .GET("/pricing/rate-cards/{book_id}/rates", {
      params: { path: { book_id: bookId }, query: params },
    })
    .then((r) => requireData(r, "Failed to load rates"));
}

export function addRate(bookId: string, body: RateInput): Promise<Rate> {
  return meteringApi
    .POST("/pricing/rate-cards/{book_id}/rates", {
      params: { path: { book_id: bookId } },
      body,
    })
    .then((r) => requireData(r, "Failed to add rate"));
}

export function deleteRate(bookId: string, rateId: string) {
  return meteringApi
    .DELETE("/pricing/rate-cards/{book_id}/rates/{rate_id}", {
      params: { path: { book_id: bookId, rate_id: rateId } },
    })
    .then((r) => requireData(r, "Failed to delete rate"));
}

export function publishBook(bookId: string, body: PublishInput): Promise<Book> {
  return meteringApi
    .POST("/pricing/rate-cards/{book_id}/publish", {
      params: { path: { book_id: bookId } },
      body,
    })
    .then((r) => requireData(r, "Failed to publish rate card"));
}

export function getMarkup(): Promise<TenantMarkup> {
  return meteringApi
    .GET("/pricing/markup")
    .then((r) => requireData(r, "Failed to load markup"));
}

export function putMarkup(body: TenantMarkupInput): Promise<TenantMarkup> {
  return meteringApi
    .PUT("/pricing/markup", { body })
    .then((r) => requireData(r, "Failed to save markup"));
}
