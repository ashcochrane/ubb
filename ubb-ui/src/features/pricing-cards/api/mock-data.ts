import type { PricingCard, Template } from "./types";

export const mockTemplates: Template[] = [
  {
    id: "gem",
    name: "Gemini 2.0 Flash",
    provider: "Google",
    dimensionCount: 3,
    pricingPattern: "token",
    dimensions: [
      { key: "input_tokens", type: "per_unit", price: 0.0000001, label: "Input tokens", unit: "per 1M tokens" },
      { key: "output_tokens", type: "per_unit", price: 0.0000004, label: "Output tokens", unit: "per 1M tokens" },
      { key: "grounding_requests", type: "flat", price: 0.035, label: "Grounding requests", unit: "per request" },
    ],
    description: "Google Gemini 2.0 Flash with grounding",
  },
  {
    id: "gpt",
    name: "GPT-4o",
    provider: "OpenAI",
    dimensionCount: 2,
    pricingPattern: "token",
    dimensions: [
      { key: "input_tokens", type: "per_unit", price: 0.0000025, label: "Input tokens", unit: "per 1M tokens" },
      { key: "output_tokens", type: "per_unit", price: 0.00001, label: "Output tokens", unit: "per 1M tokens" },
    ],
    description: "OpenAI GPT-4o",
  },
  {
    id: "claude",
    name: "Claude Sonnet",
    provider: "Anthropic",
    dimensionCount: 2,
    pricingPattern: "token",
    dimensions: [
      { key: "input_tokens", type: "per_unit", price: 0.000003, label: "Input tokens", unit: "per 1M tokens" },
      { key: "output_tokens", type: "per_unit", price: 0.000015, label: "Output tokens", unit: "per 1M tokens" },
    ],
    description: "Anthropic Claude Sonnet",
  },
];

export const mockPricingCards: PricingCard[] = [
  {
    id: "pc-001",
    cardId: "gemini_2_flash",
    name: "Gemini 2.0 Flash",
    provider: "Google",
    pricingPattern: "token",
    status: "active",
    dimensions: structuredClone(mockTemplates[0]!.dimensions),
    description: "Google Gemini 2.0 Flash with grounding requests",
    product: "property_search",
    version: 1,
    createdAt: "2026-03-01T10:00:00Z",
    updatedAt: "2026-03-01T10:00:00Z",
  },
  {
    id: "pc-002",
    cardId: "gpt_4o",
    name: "GPT-4o",
    provider: "OpenAI",
    pricingPattern: "token",
    status: "active",
    dimensions: structuredClone(mockTemplates[1]!.dimensions),
    description: "OpenAI GPT-4o for document summarisation",
    product: "doc_summariser",
    version: 2,
    createdAt: "2026-02-15T08:30:00Z",
    updatedAt: "2026-03-10T14:00:00Z",
  },
  {
    id: "pc-003",
    cardId: "serper_search",
    name: "Serper Web Search",
    provider: "Serper",
    pricingPattern: "request",
    status: "draft",
    dimensions: [
      { key: "requests", type: "flat", price: 0.001, label: "Search requests", unit: "per request" },
    ],
    version: 1,
    createdAt: "2026-04-01T09:00:00Z",
    updatedAt: "2026-04-01T09:00:00Z",
  },
];

export const mockProducts = [
  "property_search",
  "doc_summariser",
  "content_gen",
];
