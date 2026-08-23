// Mock implementation — same exported signatures as api.ts, backed by
// module-level state so mutations are coherent within a session: a declared
// book appears in the list, a declared change appears as a draft, publishing
// one writes its rules and discarding one leaves the book exactly as it was.
//
// ⚠ **IT REFUSES WHAT THE API REFUSES, AND THAT IS NOT DECORATION.** Three of
// this feature's screens exist to render a refusal — the forward horizon, a
// boundary slipping in behind one already scheduled, and discarding something
// that has already been published. A mock that accepted all three would leave
// those paths reachable only against a live server, which is the arrangement
// that let the console ship a button pointed at a deleted route once already.
// The codes are the API's own so a console mapping keyed on one is exercised
// here rather than only in production.

import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";
import {
  MOCK_BOOK_PUBLISHES,
  MOCK_COST_BOOKS,
  MOCK_GROUPING_FIELDS,
  MOCK_PRICING_BOOKS,
  MOCK_RULES,
  MOCK_TENANT_DEFAULT_MARKUP,
} from "./mock-data";
import type {
  AnyBook,
  BookChangeDiff,
  BookChangeIn,
  BookPublish,
  BookPublishIn,
  CostBook,
  CostBookIn,
  CustomerOverrideIn,
  GroupingFieldDef,
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
  Rule,
  RuleTerms,
  StatusResponse,
  TenantDefaultMarkup,
  TenantDefaultMarkupIn,
} from "./types";

// ⚠ TWO LISTS, BECAUSE THERE ARE TWO ENTITIES (#368). A single array with a
// kind field would be this mock re-inventing the column the split deleted.
let pricingBooks: PricingBook[] = MOCK_PRICING_BOOKS.map((book) => ({ ...book }));
let costBooks: CostBook[] = MOCK_COST_BOOKS.map((book) => ({ ...book }));
let rules: Rule[] = MOCK_RULES.map((rule) => ({ ...rule }));
let publishes: BookPublish[] = MOCK_BOOK_PUBLISHES.map((publish) => ({
  ...publish,
}));
let defaultMarkup: TenantDefaultMarkup = { ...MOCK_TENANT_DEFAULT_MARKUP };
let idCounter = 0;

/**
 * Put every mutable fixture back as it was declared.
 *
 * ⚠ **THIS FEATURE'S MOCK IS THE FIRST HERE WHOSE MUTATIONS ARE THE SUBJECT
 * OF THE TESTS.** Declaring, publishing and discarding all move module-level
 * state, and vitest isolates modules per FILE rather than per test — so
 * without this, "discard leaves the book unchanged" would be run against a
 * book the publish test three cases earlier had already changed, and would
 * pass or fail on the order the file happens to be written in. The referrals
 * feature set the precedent (`resetReferralsMockState`) for the same reason.
 */
export function resetPricingMockState(): void {
  pricingBooks = MOCK_PRICING_BOOKS.map((book) => ({ ...book }));
  costBooks = MOCK_COST_BOOKS.map((book) => ({ ...book }));
  rules = MOCK_RULES.map((rule) => ({ ...rule }));
  publishes = MOCK_BOOK_PUBLISHES.map((publish) => ({ ...publish }));
  defaultMarkup = { ...MOCK_TENANT_DEFAULT_MARKUP };
  idCounter = 0;
}

/** How far ahead a decision may be dated — the platform bound, not a setting. */
const MAX_FORWARD_SCHEDULING_DAYS = 366;

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
      "A cost book’s currency must match the workspace currency (usd).",
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

export async function listRules(
  bookId: string,
  params?: ListRulesParams,
): Promise<PaginatedRules> {
  await mockDelay();
  requireBook(bookId);
  let inBook = rules.filter((rule) => rule.book_id === bookId);
  if (params?.as_of) {
    const asOf = new Date(params.as_of).getTime();
    inBook = inBook.filter(
      (rule) =>
        new Date(rule.valid_from).getTime() <= asOf &&
        (rule.valid_to == null || new Date(rule.valid_to).getTime() > asOf),
    );
  } else if (!params?.include_history) {
    inBook = inBook.filter((rule) => rule.valid_to == null);
  }
  const sorted = [...inBook].sort((a, b) => b.valid_from.localeCompare(a.valid_from));
  return { data: sorted, has_more: false, next_cursor: null };
}

// --- Publishes --------------------------------------------------------------

/**
 * How a change or a diff row IDENTIFIES the rule it is about: the quantity it
 * prices, plus every selector it pins.
 *
 * ⚠ ONE SHAPE FOR BOTH, BECAUSE IT IS ONE QUESTION. A change body and the diff
 * row derived from it name the same rule, and this mock asked it of them in two
 * spellings — one looping the named selectors, one comparing them inline. That
 * is two chances to disagree about what "the same rule" means, inside the
 * module that decides what publishing does to a book.
 */
interface RuleIdentity {
  measurement_key: string;
  provider?: string | undefined;
  event_type?: string | undefined;
  task_type?: string | undefined;
  subtask_type?: string | undefined;
  grouping_fields?: Readonly<Record<string, string>> | undefined;
}

/** Whether a rule is the one an identity addresses: same quantity, same pins. */
function addresses(rule: Rule, wanted: RuleIdentity): boolean {
  if (rule.measurement_key !== wanted.measurement_key) return false;
  for (const name of ["provider", "event_type", "task_type", "subtask_type"] as const) {
    if ((rule[name] ?? "") !== (wanted[name] ?? "")) return false;
  }
  for (const field of MOCK_GROUPING_FIELDS) {
    const slot = field.slot as keyof Rule;
    const stated = wanted.grouping_fields?.[field.key] ?? "";
    if ((rule[slot] ?? "") !== stated) return false;
  }
  return true;
}

/** The live rule an identity supersedes, if there is one. */
function supersededBy(bookId: string, wanted: RuleIdentity): Rule | undefined {
  return rules.find(
    (rule) =>
      rule.book_id === bookId && rule.valid_to == null && addresses(rule, wanted),
  );
}

/** A rule's pins, keyed by the tenant's own key, with the unpinned left out. */
function pinsOf(rule: Rule): Record<string, string> {
  return Object.fromEntries(
    MOCK_GROUPING_FIELDS.map(
      (field) => [field.key, rule[field.slot as keyof Rule] as string] as const,
    ).filter(([, value]) => value !== ""),
  );
}

function termsOf(rule: Rule): RuleTerms {
  return {
    rate_structure: rule.rate_structure,
    rate_per_unit_micros: rule.rate_per_unit_micros,
    unit_quantity: rule.unit_quantity,
    fixed_micros: rule.fixed_micros,
    // The mock's rules carry no method column of their own; a rule that
    // declares none prices the event's own quantities by its own terms, which
    // is what `direct_event_price` means and what every rule on disk is today
    // (`pricing_service._priced_by_rules`).
    pricing_method: "direct_event_price",
  };
}

/**
 * The diff a declared change would have — computed the way the service does:
 * `before` is the rule as it stands, `after` is the rule the publish opens.
 *
 * A reprice carries whatever it does not state over from the rule it
 * supersedes; an add takes the model's defaults; a retire opens no rule at all
 * and its `after` is null.
 */
function diffFor(bookId: string, change: BookChangeIn): BookChangeDiff {
  const superseded = supersededBy(bookId, change);
  const before = superseded ? termsOf(superseded) : null;
  const carried = before ?? {
    rate_structure: "per_unit" as const,
    rate_per_unit_micros: 0,
    unit_quantity: 1,
    fixed_micros: 0,
    pricing_method: null,
  };
  const after: RuleTerms | null =
    change.kind === "retire"
      ? null
      : {
          rate_structure: change.rate_structure ?? carried.rate_structure,
          rate_per_unit_micros:
            change.rate_per_unit_micros ?? carried.rate_per_unit_micros,
          unit_quantity: change.unit_quantity ?? carried.unit_quantity,
          fixed_micros: change.fixed_micros ?? carried.fixed_micros,
          pricing_method: change.pricing_method ?? carried.pricing_method ?? null,
        };
  return {
    kind: change.kind,
    measurement_key: change.measurement_key,
    provider: change.provider ?? "",
    event_type: change.event_type ?? "",
    task_type: change.task_type ?? "",
    subtask_type: change.subtask_type ?? "",
    grouping_fields: { ...(change.grouping_fields ?? {}) },
    before,
    after,
  };
}

/**
 * Refuse an effective instant this platform will not honour, with the API's
 * own codes.
 *
 * ⚠ THE BOUNDARY CHECK READS THE BOOK'S OWN SCHEDULE, AND IT ADMITS AN EQUAL
 * INSTANT. A change may follow what is already scheduled or land exactly on
 * it — landing on it is how a scheduled change is reversed — and only slipping
 * in BEHIND one is refused. An implementation using `<=` here would refuse the
 * reversal this feature is built to render.
 */
function refuseAnUnhonourableInstant(bookId: string, effectiveAt?: string | null) {
  if (effectiveAt == null) return;
  const instant = new Date(effectiveAt).getTime();
  const now = Date.now();
  if (Number.isNaN(instant)) {
    throw problem(
      422,
      "validation_error",
      "Validation error",
      "effective_at is not a moment. Pick a date and time.",
    );
  }
  if (instant > now + MAX_FORWARD_SCHEDULING_DAYS * 86_400_000) {
    throw problem(
      422,
      "effective_at_too_far_ahead",
      "Validation error",
      `effective_at is more than ${MAX_FORWARD_SCHEDULING_DAYS} days ahead. ` +
        "The horizon is a platform bound and no tenant setting moves it; it " +
        "exists so that a mistyped year cannot become a schedule nobody sees " +
        "again",
    );
  }
  if (instant < now - 5 * 60_000) {
    throw problem(
      422,
      "effective_at_in_past",
      "Validation error",
      "effective_at is in the past. A change is dated forward or not at all — " +
        "omit effective_at to mean now — because a boundary behind the present " +
        "reprices work that has already been recorded",
    );
  }
  const latest = publishes
    .filter((publish) => publish.book_id === bookId)
    .map((publish) => new Date(publish.effective_at).getTime())
    .reduce((highest, candidate) => Math.max(highest, candidate), -Infinity);
  if (latest !== -Infinity && instant < latest) {
    throw problem(
      422,
      "effective_at_before_scheduled_boundary",
      "Validation error",
      "effective_at is behind a change already scheduled in this book. " +
        "Changes to one book are dated forwards: date this one at or after " +
        "that boundary, or discard the scheduled change first.",
    );
  }
}

export async function listBookPublishes(
  bookId: string,
  _params?: { cursor?: string; limit?: number },
): Promise<PaginatedBookPublishes> {
  await mockDelay();
  requireBook(bookId);
  // Drafts only, which is the route's own answer rather than a filter the
  // console applies: a published record is history, and the governance ledger
  // is where history is read.
  const pending = publishes
    .filter(
      (publish) =>
        publish.book_id === bookId && publish.declaration_status === "draft",
    )
    .sort((a, b) => a.effective_at.localeCompare(b.effective_at));
  return { data: pending, has_more: false, next_cursor: null };
}

export async function declareBookPublish(
  bookId: string,
  body: BookPublishIn,
): Promise<BookPublish> {
  await mockDelay();
  requireBook(bookId);
  refuseAnUnhonourableInstant(bookId, body.effective_at);
  if (body.changes.length === 0) {
    throw problem(
      422,
      "validation_error",
      "Validation error",
      "A change declares at least one thing to do.",
    );
  }
  const declared: BookPublish = {
    id: nextId("publish"),
    book_id: bookId,
    declaration_status: "draft",
    effective_at: body.effective_at ?? new Date().toISOString(),
    actor_kind: "member",
    actor_id: "usr_9f21c4",
    actor_display: "dana@acme.ai",
    opened_rule_ids: [],
    closed_rule_ids: [],
    published_at: null,
    diff_unavailable_reason: null,
    diff: body.changes.map((change) => diffFor(bookId, change)),
  };
  publishes = [...publishes, declared];
  return { ...declared };
}

export async function publishBookPublish(
  bookId: string,
  publishId: string,
): Promise<BookPublish> {
  await mockDelay();
  const book = requireBook(bookId);
  const draft = publishes.find(
    (candidate) => candidate.id === publishId && candidate.book_id === bookId,
  );
  if (!draft) {
    throw problem(404, "not_found", "Not found", "This change no longer exists.");
  }
  if (draft.declaration_status !== "draft") {
    throw problem(
      422,
      "validation_error",
      "Validation error",
      "This change has already been published.",
    );
  }
  const opened: string[] = [];
  const closed: string[] = [];
  for (const row of draft.diff ?? []) {
    const live = supersededBy(bookId, row);
    if (live) {
      // ⚠ CLOSED, NOT DELETED. A superseded rule keeps its row and gains an
      // end date; that is what makes a book's history readable at all, and it
      // is what a reversal reads as afterwards — three versions in a lineage,
      // the middle one closed.
      live.valid_to = draft.effective_at;
      closed.push(live.id);
    }
    if (row.after == null) continue;
    const slots: Partial<Record<keyof Rule, string>> = {};
    for (const field of MOCK_GROUPING_FIELDS) {
      slots[field.slot as keyof Rule] =
        row.grouping_fields?.[field.key] ?? "";
    }
    const openedRule = {
      id: nextId("rule"),
      book_id: bookId,
      lineage_id: live?.lineage_id ?? nextId("lineage"),
      measurement_key: row.measurement_key,
      provider: row.provider,
      event_type: row.event_type,
      task_type: row.task_type,
      subtask_type: row.subtask_type,
      grouping_field_1: "",
      grouping_field_2: "",
      grouping_field_3: "",
      grouping_field_4: "",
      grouping_field_5: "",
      grouping_field_6: "",
      grouping_field_7: "",
      grouping_field_8: "",
      grouping_field_9: "",
      grouping_field_10: "",
      ...slots,
      rate_structure: row.after.rate_structure,
      rate_per_unit_micros: row.after.rate_per_unit_micros,
      unit_quantity: row.after.unit_quantity,
      fixed_micros: row.after.fixed_micros,
      currency: "currency" in book ? book.currency : "usd",
      valid_from: draft.effective_at,
      valid_to: null,
    } as Rule;
    rules = [...rules, openedRule];
    opened.push(openedRule.id);
  }
  const published: BookPublish = {
    ...draft,
    declaration_status: "published",
    published_at: new Date().toISOString(),
    opened_rule_ids: opened,
    closed_rule_ids: closed,
    // The diff is a property of an intention. Once the rules are written the
    // record says what it DID — the two id lists above — and the contract
    // nulls the diff for exactly that reason.
    diff: null,
  };
  publishes = publishes.map((candidate) =>
    candidate.id === publishId ? published : candidate,
  );
  const bumped = { ...book, version: book.version + 1 };
  pricingBooks = pricingBooks.map((candidate) =>
    candidate.id === bookId ? (bumped as PricingBook) : candidate,
  );
  costBooks = costBooks.map((candidate) =>
    candidate.id === bookId ? (bumped as CostBook) : candidate,
  );
  return { ...published };
}

export async function discardBookPublish(
  bookId: string,
  publishId: string,
): Promise<StatusResponse> {
  await mockDelay();
  requireBook(bookId);
  const draft = publishes.find(
    (candidate) => candidate.id === publishId && candidate.book_id === bookId,
  );
  if (!draft) {
    throw problem(404, "not_found", "Not found", "This change no longer exists.");
  }
  // ⚠ A PUBLISHED RECORD IS REFUSED, and the message names the act that does
  // undo one. A draft closed nothing, so discarding it reopens nothing; a
  // publish that has already closed and opened rules is not an intention that
  // can be withdrawn.
  if (draft.declaration_status !== "draft") {
    throw problem(
      422,
      "validation_error",
      "Validation error",
      "This change has already been published. A publish is undone by a " +
        "further publish, not by discarding it.",
    );
  }
  publishes = publishes.filter((candidate) => candidate.id !== publishId);
  return { status: "discarded" };
}

// --- One customer's own rules -----------------------------------------------

export async function getInheritedRule(
  customerId: string,
  params: InheritedRuleParams,
): Promise<InheritedRule> {
  await mockDelay();
  // The same ladder one rung shorter: the customer's OWN book is taken out,
  // and what is left is what they would be charged without it.
  const theirOwn = pricingBooks.find((book) => book.customer_id === customerId);
  const selectable = pricingBooks.filter(
    (book) => book.id !== theirOwn?.id && book.is_default,
  );
  const candidates = rules.filter(
    (rule) =>
      rule.valid_to == null &&
      selectable.some((book) => book.id === rule.book_id) &&
      rule.measurement_key === params.measurement_key &&
      (rule.provider === "" || rule.provider === (params.provider ?? "")) &&
      (rule.event_type === "" || rule.event_type === (params.event_type ?? "")) &&
      MOCK_GROUPING_FIELDS.every((field) => {
        const pinned = rule[field.slot as keyof Rule];
        const asked = params.grouping_fields?.[field.key] ?? "";
        return pinned === "" || pinned === asked;
      }),
  );
  // Specificity before source: the most specific rule wins, and the source is
  // only the tie-break inside a level.
  const ranked = [...candidates].sort(
    (a, b) => specificity(b) - specificity(a),
  );
  const match = ranked[0];
  if (!match) return { rule: null };
  return {
    rule: {
      rule_id: match.id,
      book_id: match.book_id ?? "",
      measurement_key: match.measurement_key,
      provider: match.provider,
      event_type: match.event_type,
      task_type: match.task_type,
      subtask_type: match.subtask_type,
      grouping_fields: pinsOf(match),
      rate_structure: match.rate_structure,
      rate_per_unit_micros: match.rate_per_unit_micros,
      unit_quantity: match.unit_quantity,
      fixed_micros: match.fixed_micros,
      pricing_method: "direct_event_price",
      currency: match.currency,
    },
  };
}

/** How many selectors a rule pins — the ladder's major key. */
function specificity(rule: Rule): number {
  const named = ["provider", "event_type", "task_type", "subtask_type"] as const;
  return (
    named.filter((name) => rule[name] !== "").length +
    MOCK_GROUPING_FIELDS.filter(
      (field) => rule[field.slot as keyof Rule] !== "",
    ).length
  );
}

export async function declareCustomerOverride(
  customerId: string,
  body: CustomerOverrideIn,
): Promise<BookPublish> {
  await mockDelay();
  let theirOwn = pricingBooks.find((book) => book.customer_id === customerId);
  if (!theirOwn) {
    theirOwn = {
      id: nextId("book"),
      key: `customer-${customerId.slice(0, 8)}`,
      name: "Customer's own rules",
      is_default: false,
      customer_id: customerId,
      version: 1,
    };
    pricingBooks = [theirOwn, ...pricingBooks];
  }
  const { effective_at: effectiveAt, ...rule } = body;
  return declareBookPublish(theirOwn.id, {
    changes: [{ ...rule, kind: "add" }],
    effective_at: effectiveAt,
  });
}

// --- The markup rung --------------------------------------------------------

export async function getTenantDefaultMarkup(): Promise<TenantDefaultMarkup> {
  await mockDelay();
  return { ...defaultMarkup };
}

export async function declareTenantDefaultMarkup(
  body: TenantDefaultMarkupIn,
): Promise<TenantDefaultMarkup> {
  await mockDelay();
  defaultMarkup = { markup_micro_percent: body.markup_micro_percent };
  return { ...defaultMarkup };
}

export async function withdrawTenantDefaultMarkup(): Promise<StatusResponse> {
  await mockDelay();
  // ⚠ NULL, NOT ZERO. Withdrawing leaves the tenant with no rung at all, which
  // resolves to `unknown`; a zero would say they had decided to charge exactly
  // what the call cost, and nobody decided that.
  const hadOne = defaultMarkup.markup_micro_percent != null;
  defaultMarkup = { markup_micro_percent: null };
  return { status: hadOne ? "withdrawn" : "no_declaration" };
}

// --- The tenant's declared grouping vocabulary ------------------------------

export async function listGroupingFields(): Promise<GroupingFieldDef[]> {
  await mockDelay();
  return MOCK_GROUPING_FIELDS.map((field) => ({ ...field }));
}
