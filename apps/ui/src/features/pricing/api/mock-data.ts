// Coherent mock fixtures for the pricing feature (dates ~July 2026).
//
// Story: Acme AI meters LLM usage. Two COST BOOKS track what OpenAI and
// Anthropic charge them (both per-supplier defaults, each naming its supplier
// and the currency it bills in). A default PRICING BOOK bills customers ~2x
// COGS; a second, freshly declared one has no rules yet (empty-state case).
// The OpenAI cost book has already been repriced once, so one lineage carries
// a superseded historical version (history case).
//
// ⚠ THE TWO KINDS ARE TWO FIXTURES (#368), because they are two entities with
// different columns — a Pricing Book names neither a supplier nor a currency.
// One array with a kind field would be this fixture re-inventing the column
// the split deleted.

import type { CostBook, PricingBook, Rate } from "./types";

/**
 * A rate fixture, written with only the selectors this feature's story
 * actually uses (`model` maps onto `grouping_field_1`, the tenant's registered slot for
 * that grouping field) — the other nine selector columns default to ""
 * (wildcard).
 */
type RateSeed = Omit<
  Rate,
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
};

function rate(seed: RateSeed): Rate {
  const { model, ...rest } = seed;
  return {
    ...rest,
    task_type: "",
    subtask_type: "",
    grouping_field_1: model ?? "",
    grouping_field_2: "",
    grouping_field_3: "",
    grouping_field_4: "",
    grouping_field_5: "",
    grouping_field_6: "",
    grouping_field_7: "",
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
];

const OPENAI_COST_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e01";
const ANTHROPIC_COST_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e02";
const STANDARD_PRICE_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e03";

export const MOCK_RATES: Rate[] = [
  // --- OpenAI cost book -----------------------------------------------------
  rate({
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
  rate({
    // Superseded predecessor of the rate above (same lineage) — history case.
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
  rate({
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
  rate({
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
  rate({
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
  rate({
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
  rate({
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
];
