// Coherent mock fixtures for the pricing feature.
//
// Story: Acme AI meters LLM usage. Two COST BOOKS track what OpenAI and
// Anthropic charge them (both per-supplier defaults, each naming its supplier
// and the currency it bills in). A default PRICING BOOK bills customers ~2x
// COGS; a second, freshly declared one has no rules yet (empty-state case);
// a third holds one customer's own negotiated rules. The OpenAI cost book has
// already been repriced once, so one lineage carries a superseded historical
// version (history case).
//
// ⚠ THE TWO KINDS ARE TWO FIXTURES (#368), because they are two entities with
// different columns — a Pricing Book names neither a supplier nor a currency.
// One array with a kind field would be this fixture re-inventing the column
// the split deleted.
//
// ⚠ **THE SCHEDULED CHANGES ARE DATED RELATIVE TO NOW, AND EVERYTHING ELSE IS
// NOT.** A rule that took effect in June is history and a fixed date says so
// correctly forever. A change that is *about to happen* is the opposite: a
// draft pinned to a fixed instant stops being scheduled the day that instant
// passes, and then the one screen whose subject is "what is about to happen to
// my prices" demonstrates nothing. So the drafts below are offsets and the
// rules are dates.

import type {
  BookPublish,
  CostBook,
  GroupingFieldDef,
  PricingBook,
  Rule,
  TenantDefaultMarkup,
} from "./types";

/** An ISO instant a whole number of days from now, for the forward-dated half. */
export function daysFromNow(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString();
}

/**
 * This tenant's declared Grouping Field vocabulary — ALL TEN SLOTS.
 *
 * ⚠ **TEN AND NOT SIX, WHICH IS RULING 15 RENDERED (#366).** A rule can be
 * pinned on ten slots; the published contract named six until slice 4, so a
 * rule pinned on the seventh was writable server-side and unreachable through
 * the API. A fixture that declared six would leave the console demonstrating
 * exactly the gap the slice closed, and the editor's slot list is driven off
 * this registry rather than off a hand-written list for the same reason.
 */
export const MOCK_GROUPING_FIELDS: GroupingFieldDef[] = [
  "model",
  "region",
  "environment",
  "team",
  "workflow",
  "channel",
  "tier",
  "deployment",
  "pipeline",
  "cohort",
].map((key, index) => ({
  key,
  slot: `grouping_field_${index + 1}`,
  scope: "usage_event",
  max_cardinality: 200,
  retired: false,
}));

/**
 * A rule fixture, written with only the selectors this feature's story
 * actually uses — the other slots default to "" (unpinned).
 *
 * The named `model` and `region` seeds map onto slots 1 and 2, which is what
 * the registry above declares them as; the table reads the registry back to
 * label them, so neither this file nor the screen spells a slot number at a
 * tenant.
 */
type RuleSeed = Omit<
  Rule,
  | "task_type"
  | "subtask_type"
  | "grouping_field_1"
  | "grouping_field_2"
  | "grouping_field_3"
  | "grouping_field_4"
  | "grouping_field_5"
  | "grouping_field_6"
  | "grouping_field_7"
  | "grouping_field_8"
  | "grouping_field_9"
  | "grouping_field_10"
> & {
  model?: string;
  region?: string;
  /** A pin on the seventh slot, which is the one ruling 15 made reachable. */
  tier?: string;
};

function rule(seed: RuleSeed): Rule {
  const { model, region, tier, ...rest } = seed;
  return {
    ...rest,
    task_type: "",
    subtask_type: "",
    grouping_field_1: model ?? "",
    grouping_field_2: region ?? "",
    grouping_field_3: "",
    grouping_field_4: "",
    grouping_field_5: "",
    grouping_field_6: "",
    grouping_field_7: tier ?? "",
    grouping_field_8: "",
    grouping_field_9: "",
    grouping_field_10: "",
  };
}

export const MOCK_COST_BOOKS: CostBook[] = [
  {
    id: "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e01",
    key: "openai-cogs",
    name: "OpenAI provider costs",
    provider_key: "openai",
    currency: "usd",
    is_default: true,
    version: 3,
  },
  {
    id: "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e02",
    key: "anthropic-cogs",
    name: "Anthropic provider costs",
    provider_key: "anthropic",
    currency: "usd",
    is_default: true,
    version: 1,
  },
];

/** The customer whose own book holds the negotiated deal below. */
export const MOCK_OVERRIDE_CUSTOMER_ID = "7f3c2a10-9b4e-4c9a-8f21-6d5e8a301b42";

export const MOCK_PRICING_BOOKS: PricingBook[] = [
  {
    id: "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e03",
    key: "standard-price",
    name: "Standard price list",
    is_default: true,
    customer_id: null,
    version: 2,
  },
  {
    id: "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e04",
    key: "enterprise-2026",
    name: "Enterprise 2026 negotiated",
    is_default: false,
    customer_id: null,
    version: 1,
  },
  {
    // ⚠ A CUSTOMER'S OWN BOOK IS A PRICING BOOK LIKE ANY OTHER, and that is
    // the ruling rather than a fixture convenience (#361): an override is a
    // rule at a rung inside resolution, declared through a publish on this
    // book, not a number written onto the customer. Giving it its own entity
    // here would put back the record #368 deleted.
    id: "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e05",
    key: "acme-prod-own",
    name: "Acme Prod — own rules",
    is_default: false,
    customer_id: MOCK_OVERRIDE_CUSTOMER_ID,
    version: 4,
  },
];

const OPENAI_COST_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e01";
const ANTHROPIC_COST_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e02";
export const STANDARD_PRICE_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e03";
export const EMPTY_PRICING_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e04";
export const CUSTOMERS_OWN_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e05";

/** The customer's own rule, which the override editor reads and replaces. */
export const MOCK_OVERRIDE_RULE_ID = "ra1e0005-0000-4000-8000-000000000001";

export const MOCK_RULES: Rule[] = [
  // --- OpenAI cost book -----------------------------------------------------
  rule({
    id: "ra1e0001-0000-4000-8000-000000000001",
    book_id: OPENAI_COST_BOOK,
    lineage_id: "li1e0001-0000-4000-8000-000000000001",
    currency: "usd",
    measurement_key: "gpt4o_input_tokens",
    provider: "openai",
    event_type: "chat.completion",
    model: "gpt-4o",
    rate_structure: "per_unit",
    rate_per_unit_micros: 2_500_000, // $2.50 / 1M tokens
    unit_quantity: 1_000_000,
    fixed_micros: 0,
    valid_from: "2026-06-15T00:00:00Z",
    valid_to: null,
  }),
  rule({
    // Superseded predecessor of the rule above (same lineage) — history case.
    id: "ra1e0001-0000-4000-8000-000000000002",
    book_id: OPENAI_COST_BOOK,
    lineage_id: "li1e0001-0000-4000-8000-000000000001",
    currency: "usd",
    measurement_key: "gpt4o_input_tokens",
    provider: "openai",
    event_type: "chat.completion",
    model: "gpt-4o",
    rate_structure: "per_unit",
    rate_per_unit_micros: 5_000_000, // $5.00 / 1M before the June reprice
    unit_quantity: 1_000_000,
    fixed_micros: 0,
    valid_from: "2026-03-01T00:00:00Z",
    valid_to: "2026-06-15T00:00:00Z",
  }),
  rule({
    id: "ra1e0001-0000-4000-8000-000000000003",
    book_id: OPENAI_COST_BOOK,
    lineage_id: "li1e0001-0000-4000-8000-000000000003",
    currency: "usd",
    measurement_key: "gpt4o_output_tokens",
    provider: "openai",
    event_type: "chat.completion",
    model: "gpt-4o",
    rate_structure: "per_unit",
    rate_per_unit_micros: 10_000_000, // $10 / 1M tokens
    unit_quantity: 1_000_000,
    fixed_micros: 0,
    valid_from: "2026-03-01T00:00:00Z",
    valid_to: null,
  }),
  rule({
    id: "ra1e0001-0000-4000-8000-000000000004",
    book_id: OPENAI_COST_BOOK,
    lineage_id: "li1e0001-0000-4000-8000-000000000004",
    currency: "usd",
    measurement_key: "image_generation",
    provider: "openai",
    event_type: "image.generation",
    rate_structure: "fixed_component",
    rate_per_unit_micros: 0,
    unit_quantity: 1,
    fixed_micros: 40_000, // $0.04 per image
    valid_from: "2026-04-10T00:00:00Z",
    valid_to: null,
  }),
  // --- Anthropic cost book --------------------------------------------------
  rule({
    id: "ra1e0002-0000-4000-8000-000000000001",
    book_id: ANTHROPIC_COST_BOOK,
    lineage_id: "li1e0002-0000-4000-8000-000000000001",
    currency: "usd",
    measurement_key: "claude_input_tokens",
    provider: "anthropic",
    event_type: "chat.completion",
    model: "claude-sonnet",
    rate_structure: "per_unit",
    rate_per_unit_micros: 3_000_000, // $3 / 1M tokens
    unit_quantity: 1_000_000,
    fixed_micros: 0,
    valid_from: "2026-05-01T00:00:00Z",
    valid_to: null,
  }),
  // --- Standard price book --------------------------------------------------
  rule({
    id: "ra1e0003-0000-4000-8000-000000000001",
    book_id: STANDARD_PRICE_BOOK,
    lineage_id: "li1e0003-0000-4000-8000-000000000001",
    currency: "usd",
    measurement_key: "gpt4o_input_tokens",
    provider: "openai",
    event_type: "chat.completion",
    model: "gpt-4o",
    rate_structure: "per_unit",
    rate_per_unit_micros: 5_000_000, // billed at $5 / 1M
    unit_quantity: 1_000_000,
    fixed_micros: 0,
    valid_from: "2026-06-01T00:00:00Z",
    valid_to: null,
  }),
  rule({
    id: "ra1e0003-0000-4000-8000-000000000002",
    book_id: STANDARD_PRICE_BOOK,
    lineage_id: "li1e0003-0000-4000-8000-000000000002",
    currency: "usd",
    measurement_key: "gpt4o_output_tokens",
    provider: "openai",
    event_type: "chat.completion",
    model: "gpt-4o",
    rate_structure: "per_unit",
    rate_per_unit_micros: 20_000_000, // billed at $20 / 1M
    unit_quantity: 1_000_000,
    fixed_micros: 0,
    valid_from: "2026-06-01T00:00:00Z",
    valid_to: null,
  }),
  rule({
    // ⚠ PINNED ON THE SEVENTH SLOT — the reachability ruling 15 bought, shown
    // rather than asserted. A book whose every rule pinned one of the first
    // four selectors would render identically before and after the gap closed.
    id: "ra1e0003-0000-4000-8000-000000000003",
    book_id: STANDARD_PRICE_BOOK,
    lineage_id: "li1e0003-0000-4000-8000-000000000003",
    currency: "usd",
    measurement_key: "gpt4o_input_tokens",
    provider: "openai",
    event_type: "chat.completion",
    model: "gpt-4o",
    tier: "premium",
    rate_structure: "per_unit",
    rate_per_unit_micros: 8_000_000, // premium tier pays $8 / 1M
    unit_quantity: 1_000_000,
    fixed_micros: 0,
    valid_from: "2026-06-20T00:00:00Z",
    valid_to: null,
  }),
  // --- One customer's own book ---------------------------------------------
  rule({
    id: MOCK_OVERRIDE_RULE_ID,
    book_id: CUSTOMERS_OWN_BOOK,
    lineage_id: "li1e0005-0000-4000-8000-000000000001",
    currency: "usd",
    measurement_key: "gpt4o_input_tokens",
    provider: "openai",
    event_type: "chat.completion",
    model: "gpt-4o",
    rate_structure: "per_unit",
    rate_per_unit_micros: 4_000_000, // the negotiated $4 / 1M
    unit_quantity: 1_000_000,
    fixed_micros: 0,
    valid_from: "2026-07-01T00:00:00Z",
    valid_to: null,
  }),
];

/**
 * The tenant's declared markup rung — 28%, matching the receipts the events
 * feature's fixtures carry.
 *
 * ⚠ A DECLARED VALUE AND NOT A DEFAULT. UBB ships no catalogue; this workspace
 * has decided 28% and the fixture says so out loud, because the state that
 * matters most on this card is the one where the field is `null` and nothing
 * has been decided at all.
 */
export const MOCK_TENANT_DEFAULT_MARKUP: TenantDefaultMarkup = {
  markup_micro_percent: 28_000_000,
};

const ACTOR = {
  actor_kind: "member",
  actor_id: "usr_9f21c4",
  actor_display: "dana@acme.ai",
} as const;

/**
 * The changes PENDING on the standard price list — three drafts, and the three
 * are three different things a tenant needs to see.
 *
 * 1. **An immediate change carrying TWO changes in one draft.** A tenant
 *    agreeing a repricing does not agree it one rule at a time, and a book
 *    that could only take one change per publish would record a decision as
 *    several — so the diff a tenant reads before committing would never be the
 *    decision they actually made.
 * 2. **A rise dated forward**, which is the *"your book changes on 1 August;
 *    here is the diff"* case.
 * 3. **ITS REVERSAL, AT THE SAME INSTANT.** The contract permits a change to
 *    land exactly on a boundary already scheduled and says outright that this
 *    is how a scheduled change is reversed. So a reversal is a SECOND row here,
 *    after the one it undoes — the first is not removed, because a declaration
 *    somebody made is not un-made by changing your mind about it.
 */
export const MOCK_BOOK_PUBLISHES: BookPublish[] = [
  {
    id: "pub10001-0000-4000-8000-000000000001",
    book_id: STANDARD_PRICE_BOOK,
    declaration_status: "draft",
    effective_at: daysFromNow(0),
    ...ACTOR,
    opened_rule_ids: [],
    closed_rule_ids: [],
    published_at: null,
    diff_unavailable_reason: null,
    diff: [
      {
        kind: "reprice",
        measurement_key: "gpt4o_input_tokens",
        provider: "openai",
        event_type: "chat.completion",
        task_type: "",
        subtask_type: "",
        grouping_fields: { model: "gpt-4o" },
        before: {
          rate_structure: "per_unit",
          rate_per_unit_micros: 5_000_000,
          unit_quantity: 1_000_000,
          fixed_micros: 0,
          pricing_method: "direct_event_price",
        },
        after: {
          rate_structure: "per_unit",
          rate_per_unit_micros: 5_500_000,
          unit_quantity: 1_000_000,
          fixed_micros: 0,
          pricing_method: "direct_event_price",
        },
      },
      {
        kind: "add",
        measurement_key: "image_generation",
        provider: "openai",
        event_type: "image.generation",
        task_type: "",
        subtask_type: "",
        grouping_fields: {},
        before: null,
        after: {
          rate_structure: "fixed_component",
          rate_per_unit_micros: 0,
          unit_quantity: 1,
          fixed_micros: 90_000,
          pricing_method: "direct_event_price",
        },
      },
    ],
  },
  {
    id: "pub10001-0000-4000-8000-000000000002",
    book_id: STANDARD_PRICE_BOOK,
    declaration_status: "draft",
    effective_at: daysFromNow(30),
    ...ACTOR,
    opened_rule_ids: [],
    closed_rule_ids: [],
    published_at: null,
    diff_unavailable_reason: null,
    diff: [
      {
        kind: "reprice",
        measurement_key: "gpt4o_output_tokens",
        provider: "openai",
        event_type: "chat.completion",
        task_type: "",
        subtask_type: "",
        grouping_fields: { model: "gpt-4o" },
        before: {
          rate_structure: "per_unit",
          rate_per_unit_micros: 20_000_000,
          unit_quantity: 1_000_000,
          fixed_micros: 0,
          pricing_method: "direct_event_price",
        },
        after: {
          rate_structure: "per_unit",
          rate_per_unit_micros: 24_000_000,
          unit_quantity: 1_000_000,
          fixed_micros: 0,
          pricing_method: "direct_event_price",
        },
      },
    ],
  },
  {
    id: "pub10001-0000-4000-8000-000000000003",
    book_id: STANDARD_PRICE_BOOK,
    declaration_status: "draft",
    // The same instant as the rise above, which is what makes it a reversal
    // rather than a further change: the contract admits a boundary landing
    // exactly on one already scheduled for precisely this act.
    effective_at: daysFromNow(30),
    ...ACTOR,
    opened_rule_ids: [],
    closed_rule_ids: [],
    published_at: null,
    diff_unavailable_reason: null,
    diff: [
      {
        kind: "reprice",
        measurement_key: "gpt4o_output_tokens",
        provider: "openai",
        event_type: "chat.completion",
        task_type: "",
        subtask_type: "",
        grouping_fields: { model: "gpt-4o" },
        before: {
          rate_structure: "per_unit",
          rate_per_unit_micros: 24_000_000,
          unit_quantity: 1_000_000,
          fixed_micros: 0,
          pricing_method: "direct_event_price",
        },
        after: {
          rate_structure: "per_unit",
          rate_per_unit_micros: 20_000_000,
          unit_quantity: 1_000_000,
          fixed_micros: 0,
          pricing_method: "direct_event_price",
        },
      },
    ],
  },
];
