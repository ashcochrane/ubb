// Mock implementation — same exported signatures as api.ts, backed by
// module-level state so mutations are coherent within a session: created
// books appear in the list and markup edits stick.
//
// ⚠ IT NO LONGER SUPERSEDES RATES (#368). The immediate reprice this mocked is
// deleted with the route it stood for; a book changes by a declared publish
// now, and the feature that speaks that body arrives with #372.

import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";
import {
  MOCK_COST_BOOKS,
  MOCK_PRICING_BOOKS,
  MOCK_RATES,
  MOCK_TENANT_MARKUP,
} from "./mock-data";
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
  Rate,
  TenantMarkup,
  TenantMarkupIn,
} from "./types";

// ⚠ TWO LISTS, BECAUSE THERE ARE TWO ENTITIES (#368). A single array with a
// kind field would be this mock re-inventing the column the split deleted.
let pricingBooks: PricingBook[] = MOCK_PRICING_BOOKS.map((book) => ({ ...book }));
let costBooks: CostBook[] = MOCK_COST_BOOKS.map((book) => ({ ...book }));
const rates: Rate[] = MOCK_RATES.map((rate) => ({ ...rate }));
let markup: TenantMarkup = { ...MOCK_TENANT_MARKUP };
let idCounter = 0;

function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-mock-${String(idCounter).padStart(4, "0")}`;
}

function problem(status: number, code: string, title: string, detail: string): ApiProblem {
  return new ApiProblem({ status, code, title, detail });
}

function requireBook(bookId: string): AnyBook {
  const book = [...pricingBooks, ...costBooks].find(
    (candidate) => candidate.id === bookId,
  );
  if (!book) {
    throw problem(404, "not_found", "Not found", "This book no longer exists.");
  }
  return book;
}

export async function listPricingBooks(
  _params?: ListBooksParams,
): Promise<PaginatedPricingBooks> {
  await mockDelay();
  return { data: [...pricingBooks], has_more: false, next_cursor: null };
}

export async function listCostBooks(
  _params?: ListBooksParams,
): Promise<PaginatedCostBooks> {
  await mockDelay();
  return { data: [...costBooks], has_more: false, next_cursor: null };
}

export async function declarePricingBook(
  body: PricingBookIn,
): Promise<PricingBook> {
  await mockDelay();
  if (pricingBooks.some((book) => book.key === body.key)) {
    throw problem(
      409,
      "conflict",
      "Conflict",
      `A pricing book with the key "${body.key}" already exists.`,
    );
  }
  if (body.is_default && pricingBooks.some((book) => book.is_default)) {
    throw problem(
      409,
      "conflict",
      "Conflict",
      "This workspace already has a default pricing book.",
    );
  }
  const created: PricingBook = {
    id: nextId("book"),
    key: body.key,
    name: body.name ?? "",
    is_default: body.is_default ?? false,
    customer_id: null,
    version: 1,
  };
  pricingBooks = [created, ...pricingBooks];
  return { ...created };
}

export async function declareCostBook(body: CostBookIn): Promise<CostBook> {
  await mockDelay();
  if (costBooks.some((book) => book.key === body.key)) {
    throw problem(
      409,
      "conflict",
      "Conflict",
      `A cost book with the key "${body.key}" already exists.`,
    );
  }
  if (body.currency && body.currency !== "usd") {
    throw problem(
      422,
      "validation_error",
      "Validation error",
      "A cost book\u2019s currency must match the workspace currency (usd).",
    );
  }
  const created: CostBook = {
    id: nextId("book"),
    key: body.key,
    name: body.name ?? "",
    provider_key: body.provider_key ?? "",
    currency: "usd",
    is_default: body.is_default ?? false,
    version: 1,
  };
  costBooks = [created, ...costBooks];
  return { ...created };
}

export async function getBook(bookId: string): Promise<AnyBook> {
  await mockDelay();
  return { ...requireBook(bookId) };
}

export async function listRates(
  bookId: string,
  params?: ListRatesParams,
): Promise<PaginatedRates> {
  await mockDelay();
  requireBook(bookId);
  let inBook = rates.filter((rate) => rate.book_id === bookId);
  if (params?.as_of) {
    const asOf = new Date(params.as_of).getTime();
    inBook = inBook.filter(
      (rate) =>
        new Date(rate.valid_from).getTime() <= asOf &&
        (rate.valid_to == null || new Date(rate.valid_to).getTime() > asOf),
    );
  } else if (!params?.include_history) {
    inBook = inBook.filter((rate) => rate.valid_to == null);
  }
  const sorted = [...inBook].sort((a, b) => b.valid_from.localeCompare(a.valid_from));
  return { data: sorted, has_more: false, next_cursor: null };
}

export async function getTenantMarkup(): Promise<TenantMarkup> {
  await mockDelay();
  return { ...markup };
}

export async function putTenantMarkup(body: TenantMarkupIn): Promise<TenantMarkup> {
  await mockDelay();
  markup = {
    markup_percentage_micros: body.markup_percentage_micros ?? 0,
    fixed_uplift_micros: body.fixed_uplift_micros ?? 0,
  };
  return { ...markup };
}
