// Pricing feature — type aliases over the generated contract schemas.
// Every response used by this feature is a fully named component schema, so
// no local "[backend-verified shape]" interfaces are needed here.

import type { MeteringSchemas } from "@/api/types";

// ⚠ THE CONTAINER IS TWO ENTITIES (#368). A Pricing Book is a catalogue of
// what this tenant charges and names neither a supplier nor a currency; a cost
// book records what one supplier charges and names both. They are separate
// component schemas because they are separate things, and one FLATTENED `Book`
// type carrying every field of both — a supplier that is sometimes there, a
// currency that is sometimes meaningful — would put back exactly the
// conflation the split removed. `AnyBook` below is not that: it is a union a
// caller must narrow before it can read anything only one side has, which is
// the difference the compiler enforces.
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

/**
 * One rule, as a book holds it.
 *
 * ⚠ **THE WIRE CALLS THE ROW A RATE AND THE SCREENS CALL IT A RULE, AND BOTH
 * ARE RIGHT.** `RateOut` is the published component schema and this commit
 * makes no contract change, so the alias is the contract's own name; what a
 * tenant reads is the domain's — `BookChangeIn` calls the thing it changes a
 * rule, `InheritedPricingRule` is a rule, and the governance ledger records
 * `pricing_rule.added`. Aliasing the schema to something the contract does not
 * call it would hide which schema a reader is looking at; spelling the wire's
 * word on a screen would put a transport detail in front of a tenant.
 */
export type Rule = MeteringSchemas["RateOut"];
// ⚠ NO `RateIn` (#367) AND NO `RateChangeIn` (#368). Both bodies that wrote a
// rule immediately are deleted from the contract with their routes: adding,
// repricing and retiring a rule are declared changes on a publish now, and
// `BookChangeIn` below is the body that says so.
export type PaginatedRules = MeteringSchemas["PaginatedRates"];

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

/**
 * How a rule DERIVES its price — a margin over what the call cost, or an
 * amount attached to the event.
 *
 * ⚠ **A DIFFERENT FACT FROM THE ARITHMETIC SHAPE ABOVE**, and the two are a
 * near miss in a reader's head rather than in the code. `rate_structure` says
 * which of the money terms is spent; `pricing_method` says where the number
 * came from. `BookChangeIn` says outright that a change may move either without
 * the other, which is only expressible because they are two fields — and the
 * rule editor keeps them two controls for the same reason.
 */
export type { PricingMethod } from "@/lib/vocabulary";

// --- Publishes: the one way a book changes ----------------------------------

/**
 * A change to a book: an intention while it is a draft, a decision once
 * published.
 *
 * ONE TYPE AND NOT TWO, because it is one record. `declaration_status` says
 * which of the two it is, `diff` is populated while it is still a draft, and
 * `published_at` is what turns the row into history. A separate `Draft` type
 * would be the same row wearing a second name, and the screens would then have
 * to agree with each other about which name a row had at any moment.
 */
export type BookPublish = MeteringSchemas["BookPublishOut"];
export type BookPublishIn = MeteringSchemas["BookPublishIn"];
export type PaginatedBookPublishes = MeteringSchemas["PaginatedBookPublishes"];

/** One change inside a publish: what to do, and to which rule. */
export type BookChangeIn = MeteringSchemas["BookChangeIn"];

/** One row of a draft's diff — the rule, and what happens to it. */
export type BookChangeDiff = MeteringSchemas["BookChangeDiffOut"];

/** What a rule charges, how it derives it, and which arithmetic it runs. */
export type RuleTerms = MeteringSchemas["RuleTermsOut"];

// --- The customer's own rules -----------------------------------------------

/** What a customer is charged where they have no rule of their own. */
export type InheritedRule = MeteringSchemas["InheritedRuleOut"];
export type InheritedPricingRule = MeteringSchemas["InheritedPricingRule"];

/** The whole rule one customer gets, and when it takes effect. */
export type CustomerOverrideIn = MeteringSchemas["CustomerOverrideIn"];

// --- The markup rung --------------------------------------------------------

/**
 * The tenant's declared default markup rung — what prices an event no rule
 * matched.
 *
 * ⚠ **ITS AMOUNT IS NULLABLE AND NULL IS NOT ZERO.** A declared zero says
 * *charge my customer exactly what the call cost* and settles; no declaration
 * at all means nobody has said what to charge, and the price resolves to
 * `unknown` with no amount. The contract spends a paragraph on the difference
 * and the console owes it the same care — which is why the card that renders
 * this never coalesces the field.
 */
export type TenantDefaultMarkup = MeteringSchemas["TenantDefaultMarkupOut"];
export type TenantDefaultMarkupIn = MeteringSchemas["TenantDefaultMarkupIn"];

// --- The tenant's declared grouping vocabulary ------------------------------

/**
 * The tenant's own Grouping Field declarations, which is how a rule reaches
 * past the four named selectors.
 *
 * ⚠ **ALL TEN SLOTS, WHICH IS RULING 15's WHOLE POINT (#366).** A rule may be
 * pinned on ten grouping slots and the published contract once named six, so a
 * rule pinned on the seventh could be written server-side and never repriced
 * through the API. The gap left with slice 4, and a change body now carries
 * `grouping_fields` as a map keyed by the tenant's DECLARED key rather than a
 * fixed list of properties. The editor therefore offers whatever this registry
 * declares — anywhere from none to ten — instead of a hand-written six that
 * would be the same bug written in the console.
 */
export type GroupingFieldRegistry = MeteringSchemas["DimensionRegistryOut"];
export type GroupingFieldDef = MeteringSchemas["DimensionDefOut"];

export type StatusResponse = MeteringSchemas["StatusResponse"];

/** Query options for either books list. */
export interface ListBooksParams {
  cursor?: string;
  limit?: number;
}

/** Query options for a book's rules list. */
export interface ListRulesParams {
  /** Include superseded/retired versions (rows carrying a valid_to). */
  include_history?: boolean;
  /** Point-in-time view (ISO datetime). Takes precedence over include_history. */
  as_of?: string;
  cursor?: string;
  limit?: number;
}

/** Which rule to ask the inherited-rule route about. */
export interface InheritedRuleParams {
  measurement_key: string;
  provider?: string;
  event_type?: string;
  task_type?: string;
  subtask_type?: string;
  /** One entry per pinned grouping field, keyed by the tenant's own key. */
  grouping_fields?: Readonly<Record<string, string>>;
  as_of?: string;
}
