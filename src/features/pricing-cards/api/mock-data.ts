import type { PricingCard, Template, DimensionInput } from "./types";
import type { GroupSummary } from "./api";

// Pre-built dimension snippets used by both templates and seed cards.
const tokenInputDim: DimensionInput = {
  metricName: "input_tokens",
  pricingType: "per_unit",
  costPerUnitMicros: 3_000,
  providerCostPerUnitMicros: 2_500,
  unitQuantity: 1_000_000,
  currency: "USD",
  label: "Input tokens",
  unit: "per 1M tokens",
};

const tokenOutputDim: DimensionInput = {
  metricName: "output_tokens",
  pricingType: "per_unit",
  costPerUnitMicros: 15_000,
  providerCostPerUnitMicros: 10_000,
  unitQuantity: 1_000_000,
  currency: "USD",
  label: "Output tokens",
  unit: "per 1M tokens",
};

const flatRequestDim: DimensionInput = {
  metricName: "requests",
  pricingType: "flat",
  costPerUnitMicros: 1_500,
  providerCostPerUnitMicros: 1_000,
  unitQuantity: 1,
  currency: "USD",
  label: "Search request",
  unit: "per request",
};

export const mockTemplates: Template[] = [
  {
    id: "tpl-gpt-4o",
    name: "GPT-4o",
    provider: "OpenAI",
    description: "OpenAI GPT-4o (token-based)",
    dimensions: [tokenInputDim, tokenOutputDim],
  },
  {
    id: "tpl-claude-sonnet",
    name: "Claude Sonnet",
    provider: "Anthropic",
    description: "Anthropic Claude Sonnet",
    dimensions: [
      { ...tokenInputDim, costPerUnitMicros: 3_500, providerCostPerUnitMicros: 3_000 },
      { ...tokenOutputDim, costPerUnitMicros: 18_000, providerCostPerUnitMicros: 15_000 },
    ],
  },
  {
    id: "tpl-serper",
    name: "Serper Web Search",
    provider: "Serper",
    description: "Web search request",
    dimensions: [flatRequestDim],
  },
];

// Helper: convert a DimensionInput[] into a Dimension[] (adds id, valid timestamps).
const dimsFromInputs = (
  inputs: DimensionInput[],
  cardSlug: string,
): PricingCard["dimensions"] =>
  inputs.map((d, i) => ({
    ...d,
    id: `dim-${cardSlug}-${i}`,
    validFrom: "2026-03-01T10:00:00Z",
    validTo: null,
  }));

export const mockPricingCards: PricingCard[] = [
  {
    id: "pc-001",
    slug: "gpt_4o",
    name: "GPT-4o",
    provider: "OpenAI",
    description: "OpenAI GPT-4o for document summarisation",
    pricingSourceUrl: "https://openai.com/pricing",
    groupId: "grp-001",
    groupName: "Document AI",
    status: "active",
    dimensions: dimsFromInputs([tokenInputDim, tokenOutputDim], "gpt_4o"),
    createdAt: "2026-02-15T08:30:00Z",
    updatedAt: "2026-03-10T14:00:00Z",
  },
  {
    id: "pc-002",
    slug: "claude_sonnet",
    name: "Claude Sonnet",
    provider: "Anthropic",
    description: "Anthropic Claude Sonnet for chat",
    pricingSourceUrl: "https://www.anthropic.com/pricing",
    groupId: "grp-001",
    groupName: "Document AI",
    status: "active",
    dimensions: dimsFromInputs(
      [
        { ...tokenInputDim, costPerUnitMicros: 3_500, providerCostPerUnitMicros: 3_000 },
        { ...tokenOutputDim, costPerUnitMicros: 18_000, providerCostPerUnitMicros: 15_000 },
      ],
      "claude_sonnet",
    ),
    createdAt: "2026-03-01T10:00:00Z",
    updatedAt: "2026-03-01T10:00:00Z",
  },
  {
    id: "pc-003",
    slug: "serper_search",
    name: "Serper Web Search",
    provider: "Serper",
    description: "Web search requests",
    pricingSourceUrl: "",
    groupId: null,
    groupName: null,
    status: "draft",
    dimensions: dimsFromInputs([flatRequestDim], "serper_search"),
    createdAt: "2026-04-01T09:00:00Z",
    updatedAt: "2026-04-01T09:00:00Z",
  },
];

export const mockGroups: GroupSummary[] = [
  { id: "grp-001", name: "Document AI", slug: "document_ai", marginPct: 25 },
  { id: "grp-002", name: "Search", slug: "search", marginPct: 15 },
];
