// Mock implementation — same exported signatures as api.ts, backed by
// module-level state so mutations are coherent within a session: created
// books appear in the list, retired rates gain a valid_to, publishes
// supersede actives and bump the book version, markup edits stick.

import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";
import { MOCK_BOOKS, MOCK_RATES, MOCK_TENANT_MARKUP } from "./mock-data";
import type {
  Book,
  BookIn,
  ListBooksParams,
  ListRatesParams,
  PaginatedBooks,
  PaginatedRates,
  PublishIn,
  Rate,
  TenantMarkup,
  TenantMarkupIn,
} from "./types";

let books: Book[] = MOCK_BOOKS.map((book) => ({ ...book }));
let rates: Rate[] = MOCK_RATES.map((rate) => ({ ...rate }));
let markup: TenantMarkup = { ...MOCK_TENANT_MARKUP };
let idCounter = 0;

function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-mock-${String(idCounter).padStart(4, "0")}`;
}

function problem(status: number, code: string, title: string, detail: string): ApiProblem {
  return new ApiProblem({ status, code, title, detail });
}

function requireBook(bookId: string): Book {
  const book = books.find((candidate) => candidate.id === bookId);
  if (!book) {
    throw problem(404, "not_found", "Not found", "This rate-card book no longer exists.");
  }
  return book;
}

/** The ten selector columns (provider/event_type handled by the caller). */
interface Selectors {
  task_type?: string | null;
  subtask_type?: string | null;
  grouping_field_1?: string | null;
  grouping_field_2?: string | null;
  grouping_field_3?: string | null;
  grouping_field_4?: string | null;
  grouping_field_5?: string | null;
  grouping_field_6?: string | null;
  grouping_field_7?: string | null;
  grouping_field_8?: string | null;
  grouping_field_9?: string | null;
  grouping_field_10?: string | null;
}

const SELECTOR_KEYS = [
  "task_type",
  "subtask_type",
  "grouping_field_1",
  "grouping_field_2",
  "grouping_field_3",
  "grouping_field_4",
  "grouping_field_5",
  "grouping_field_6",
  "grouping_field_7",
  "grouping_field_8",
  "grouping_field_9",
  "grouping_field_10",
] as const;

function sameSelectors(a: Selectors, b: Selectors): boolean {
  return SELECTOR_KEYS.every((key) => (a[key] ?? "") === (b[key] ?? ""));
}

export async function listBooks(params?: ListBooksParams): Promise<PaginatedBooks> {
  await mockDelay();
  const filtered = params?.card_type
    ? books.filter((book) => book.card_type === params.card_type)
    : books;
  return { data: [...filtered], has_more: false, next_cursor: null };
}

export async function createBook(body: BookIn): Promise<Book> {
  await mockDelay();
  if (books.some((book) => book.key === body.key && book.card_type === body.card_type)) {
    throw problem(
      409,
      "conflict",
      "Conflict",
      `A ${body.card_type} book with the key "${body.key}" already exists.`,
    );
  }
  if (body.currency && body.currency !== "usd") {
    throw problem(
      422,
      "validation_error",
      "Validation error",
      "Rate-card currency must match the workspace currency (usd).",
    );
  }
  const created: Book = {
    id: nextId("book"),
    key: body.key,
    name: body.name ?? "",
    card_type: body.card_type,
    provider_key: body.provider_key ?? "",
    currency: "usd",
    is_default: body.is_default ?? false,
    version: 1,
  };
  books = [created, ...books];
  return { ...created };
}

export async function getBook(bookId: string): Promise<Book> {
  await mockDelay();
  return { ...requireBook(bookId) };
}

export async function listRates(
  bookId: string,
  params?: ListRatesParams,
): Promise<PaginatedRates> {
  await mockDelay();
  requireBook(bookId);
  let inBook = rates.filter((rate) => rate.rate_card_id === bookId);
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

export async function publishBook(bookId: string, body: PublishIn): Promise<Book> {
  await mockDelay();
  const book = requireBook(bookId);
  const now = new Date().toISOString();
  const superseded: { old: Rate; next: Rate }[] = [];
  for (const change of body.changes) {
    const active = rates.find(
      (rate) =>
        rate.rate_card_id === bookId &&
        rate.valid_to == null &&
        rate.measurement_key === change.measurement_key &&
        rate.provider === (change.provider ?? "") &&
        rate.event_type === (change.event_type ?? "") &&
        sameSelectors(rate, change),
    );
    if (!active) {
      throw problem(
        422,
        "validation_error",
        "Validation error",
        `No active rate matches "${change.measurement_key}" — nothing was changed.`,
      );
    }
    superseded.push({
      old: active,
      next: {
        ...active,
        id: nextId("rate"),
        rate_structure: change.rate_structure ?? active.rate_structure,
        rate_per_unit_micros: change.rate_per_unit_micros ?? active.rate_per_unit_micros,
        unit_quantity: change.unit_quantity ?? active.unit_quantity,
        fixed_micros: change.fixed_micros ?? active.fixed_micros,
        valid_from: now,
        valid_to: null,
      },
    });
  }
  // All-or-nothing: apply only after every change matched.
  for (const { old, next } of superseded) {
    old.valid_to = now;
    rates = [next, ...rates];
  }
  book.version += 1;
  return { ...book };
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
