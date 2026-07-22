// src/features/export/api/mock-data.ts
import type {
  ExportFilterOptions,
  PreviewColumn,
} from "./types";

export const mockFilterOptions: ExportFilterOptions = {
  customers: [
    { id: "1", name: "Acme Corp", eventCount: 14_219 },
    { id: "2", name: "BrightPath Ltd", eventCount: 11_402 },
    { id: "3", name: "NovaTech Inc", eventCount: 6_841 },
    { id: "4", name: "Helios Digital", eventCount: 9_403 },
    { id: "5", name: "Zenith Labs", eventCount: 5_120 },
    { id: "6", name: "ClearView Analytics", eventCount: 8_210 },
    { id: "7", name: "Eko Systems", eventCount: 7_891 },
    { id: "8", name: "Pinnacle AI", eventCount: 2_104 },
    { id: "9", name: "Meridian Group", eventCount: 3_812 },
    { id: "10", name: "Atlas Robotics", eventCount: 2_310 },
    { id: "11", name: "Quantum Logic", eventCount: 1_891 },
    { id: "12", name: "BlueSky Data", eventCount: 1_402 },
    { id: "13", name: "Vertex Labs", eventCount: 980 },
    { id: "14", name: "Forge AI", eventCount: 820 },
    { id: "15", name: "Echo Systems", eventCount: 650 },
    { id: "16", name: "Ridgeline", eventCount: 410 },
    { id: "17", name: "Prism Health", eventCount: 220 },
    { id: "18", name: "Aether Inc", eventCount: 102 },
  ],
  products: [
    { key: "property_search", label: "Property search", percentage: 68 },
    { key: "doc_summariser", label: "Doc summariser", percentage: 22 },
    { key: "content_gen", label: "Content gen", percentage: 10 },
  ],
  cards: [
    { key: "gemini_2_flash", label: "Gemini 2.0 Flash", percentage: 55 },
    { key: "claude_sonnet", label: "Claude Sonnet", percentage: 25 },
    { key: "gpt_4o", label: "GPT-4o", percentage: 12 },
    { key: "google_places", label: "Google Places", percentage: 5 },
    { key: "serper", label: "Serper", percentage: 3 },
  ],
};

export const dimensionColumns: PreviewColumn[] = [
  { key: "eventTime", label: "event_time" },
  { key: "customer", label: "customer" },
  { key: "product", label: "product" },
  { key: "pricingCard", label: "pricing_card" },
  { key: "cardVersion", label: "card_version" },
  { key: "dimension", label: "dimension", muted: true },
  { key: "quantity", label: "quantity", align: "right" },
  { key: "unitPrice", label: "unit_price", align: "right" },
  { key: "cost", label: "cost", align: "right", bold: true },
  { key: "eventTotal", label: "event_total", align: "right", bold: true },
];

export const dimensionRows: Record<string, string | number | null>[] = [
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "gemini_2_flash", cardVersion: "v3", dimension: "input_tokens", quantity: "1,842", unitPrice: "0.0000001500", cost: "0.000276", eventTotal: "0.035847" },
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "gemini_2_flash", cardVersion: "v3", dimension: "output_tokens", quantity: "623", unitPrice: "0.0000004000", cost: "0.000249", eventTotal: "0.035847" },
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "gemini_2_flash", cardVersion: "v3", dimension: "grounding_requests", quantity: "1", unitPrice: "0.0350000000", cost: "0.035000", eventTotal: "0.035847" },
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "google_places", cardVersion: "v1", dimension: "requests", quantity: "1", unitPrice: "0.0320000000", cost: "0.032000", eventTotal: "0.032000" },
  { eventTime: "2026-03-20 14:22:58", customer: "brightpath", product: "doc_summariser", pricingCard: "claude_35_sonnet", cardVersion: "v2", dimension: "input_tokens", quantity: "4,210", unitPrice: "0.0000030000", cost: "0.012630", eventTotal: "0.040335" },
];

export const eventColumns: PreviewColumn[] = [
  { key: "eventTime", label: "event_time" },
  { key: "customer", label: "customer" },
  { key: "product", label: "product" },
  { key: "pricingCard", label: "pricing_card" },
  { key: "cardVersion", label: "card_version" },
  { key: "inputTokens", label: "input_tokens", align: "right" },
  { key: "outputTokens", label: "output_tokens", align: "right" },
  { key: "groundingReqs", label: "grounding_reqs", align: "right" },
  { key: "requests", label: "requests", align: "right" },
  { key: "totalCost", label: "total_cost", align: "right", bold: true },
];

export const eventRows: Record<string, string | number | null>[] = [
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "gemini_2_flash", cardVersion: "v3", inputTokens: "1,842", outputTokens: "623", groundingReqs: "1", requests: null, totalCost: "0.035847" },
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "google_places", cardVersion: "v1", inputTokens: null, outputTokens: null, groundingReqs: null, requests: "1", totalCost: "0.032000" },
  { eventTime: "2026-03-20 14:22:58", customer: "brightpath", product: "doc_summariser", pricingCard: "claude_35_sonnet", cardVersion: "v2", inputTokens: "4,210", outputTokens: "1,847", groundingReqs: null, requests: null, totalCost: "0.040335" },
  { eventTime: "2026-03-20 14:22:55", customer: "novatech", product: "property_search", pricingCard: "gemini_2_flash", cardVersion: "v3", inputTokens: "986", outputTokens: "412", groundingReqs: "1", requests: null, totalCost: "0.035321" },
  { eventTime: "2026-03-20 14:22:51", customer: "helios", product: "content_gen", pricingCard: "gpt_4o", cardVersion: "v1", inputTokens: "2,105", outputTokens: "3,241", groundingReqs: null, requests: null, totalCost: "0.037685" },
];

/** Product key to fraction of total events */
export const productPcts: Record<string, number> = {
  property_search: 0.68,
  doc_summariser: 0.22,
  content_gen: 0.10,
};

/** Card key to fraction of total events */
export const cardPcts: Record<string, number> = {
  gemini_2_flash: 0.55,
  claude_sonnet: 0.25,
  gpt_4o: 0.12,
  google_places: 0.05,
  serper: 0.03,
};
