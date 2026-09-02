// Mock fixtures for the tasks feature — one coherent story, September 2026.
//
// Acme AI (the tenant) has declared seven kinds of work. Three are sold at one
// agreed price, and the runs beneath them are what lets the console show a
// ceiling AGAINST a price (#150 §5.4): a run pins the price it was quoted at
// start, and that pinned figure is the only wire-borne evidence of what a kind
// of work sells for — the amount itself is a line in a pricing book, resolved
// per customer, and the registry deliberately does not carry it (#415).
//
//   document-summary    task     event priced   the ordinary kind
//   video-render        task     fixed          three runs, all quoted $5.00
//   transcript-cleanup  task     fixed          two runs at $4.00 and $8.00 —
//                                               one customer's own book prices it
//                                               higher, so the ceiling is a
//                                               different share of each
//   image-upscale       task     fixed          declared, never run
//   render-frame        subtask  event priced   inherits the workspace ceiling
//   legacy-ocr          task     event priced   retired
//   translate           BOTH altitudes share the word — two declarations

import type { KindOfWork, RunRow } from "./types";

export const KIND_EVENT_PRICED_KEY = "document-summary";
export const KIND_FIXED_KEY = "video-render";
export const KIND_FIXED_NEGOTIATED_KEY = "transcript-cleanup";
export const KIND_FIXED_UNSOLD_KEY = "image-upscale";
export const KIND_STEP_KEY = "render-frame";
export const KIND_RETIRED_KEY = "legacy-ocr";
export const KIND_SHARED_WORD_KEY = "translate";

/** The one price every `video-render` run so far was quoted. */
export const VIDEO_RENDER_PRICE_MICROS = 5_000_000;
/** The COGS ceiling declared on `video-render` — 60% of that price. */
export const VIDEO_RENDER_CEILING_MICROS = 3_000_000;

export const TRANSCRIPT_LOW_PRICE_MICROS = 4_000_000;
export const TRANSCRIPT_HIGH_PRICE_MICROS = 8_000_000;
export const TRANSCRIPT_CEILING_MICROS = 3_000_000;

export const MOCK_KINDS: readonly KindOfWork[] = [
  {
    key: KIND_EVENT_PRICED_KEY,
    kind: "task",
    pricing_mode: "event_priced",
    default_provider_cost_limit_micros: 2_000_000,
    silence_window_seconds: 600,
    absolute_deadline_seconds: null,
    required_dimensions: ["model"],
    retired: false,
    retired_at: null,
  },
  {
    key: KIND_FIXED_KEY,
    kind: "task",
    pricing_mode: "fixed",
    default_provider_cost_limit_micros: VIDEO_RENDER_CEILING_MICROS,
    silence_window_seconds: 1_800,
    absolute_deadline_seconds: 7_200,
    required_dimensions: [],
    retired: false,
    retired_at: null,
  },
  {
    key: KIND_FIXED_NEGOTIATED_KEY,
    kind: "task",
    pricing_mode: "fixed",
    default_provider_cost_limit_micros: TRANSCRIPT_CEILING_MICROS,
    silence_window_seconds: 900,
    absolute_deadline_seconds: null,
    required_dimensions: [],
    retired: false,
    retired_at: null,
  },
  {
    key: KIND_FIXED_UNSOLD_KEY,
    kind: "task",
    pricing_mode: "fixed",
    default_provider_cost_limit_micros: 1_500_000,
    silence_window_seconds: null,
    absolute_deadline_seconds: null,
    required_dimensions: [],
    retired: false,
    retired_at: null,
  },
  {
    key: KIND_STEP_KEY,
    kind: "subtask",
    pricing_mode: "event_priced",
    default_provider_cost_limit_micros: null,
    silence_window_seconds: null,
    absolute_deadline_seconds: null,
    required_dimensions: [],
    retired: false,
    retired_at: null,
  },
  {
    key: KIND_RETIRED_KEY,
    kind: "task",
    pricing_mode: "event_priced",
    default_provider_cost_limit_micros: 500_000,
    silence_window_seconds: 300,
    absolute_deadline_seconds: null,
    required_dimensions: [],
    retired: true,
    retired_at: "2026-06-30T09:00:00Z",
  },
  {
    key: KIND_SHARED_WORD_KEY,
    kind: "task",
    pricing_mode: "event_priced",
    default_provider_cost_limit_micros: 1_000_000,
    silence_window_seconds: 600,
    absolute_deadline_seconds: null,
    required_dimensions: [],
    retired: false,
    retired_at: null,
  },
  {
    key: KIND_SHARED_WORD_KEY,
    kind: "subtask",
    pricing_mode: "event_priced",
    default_provider_cost_limit_micros: 250_000,
    silence_window_seconds: null,
    absolute_deadline_seconds: null,
    required_dimensions: [],
    retired: false,
    retired_at: null,
  },
];

function run(
  overrides: Partial<RunRow> & Pick<RunRow, "task_id" | "task_type" | "created_at">,
): RunRow {
  return {
    status: "completed",
    total_provider_cost_micros: 0,
    unresolved_event_count: 0,
    total_billed_cost_micros: 0,
    unpriced_event_count: 0,
    event_count: 0,
    ...overrides,
  };
}

/** Top-level runs, newest first — the order the route answers in. */
export const MOCK_RUNS: readonly RunRow[] = [
  run({
    task_id: "6e1f2c8a-3b47-4d90-a5e2-7c9d0b1f3a64",
    task_type: KIND_FIXED_KEY,
    status: "active",
    agreed_price_micros: VIDEO_RENDER_PRICE_MICROS,
    provider_cost_limit_micros: VIDEO_RENDER_CEILING_MICROS,
    total_provider_cost_micros: 1_240_000,
    event_count: 12,
    created_at: "2026-09-01T14:05:00Z",
  }),
  run({
    task_id: "0b7d4e29-8f13-4a6c-b0d5-2e8a9c4f7b13",
    task_type: KIND_FIXED_NEGOTIATED_KEY,
    agreed_price_micros: TRANSCRIPT_HIGH_PRICE_MICROS,
    provider_cost_limit_micros: TRANSCRIPT_CEILING_MICROS,
    total_provider_cost_micros: 2_100_000,
    event_count: 30,
    created_at: "2026-08-31T18:40:00Z",
    completed_at: "2026-08-31T18:52:00Z",
  }),
  run({
    task_id: "9c3a5f71-2d86-4b04-8e19-5a7c1d0e2f95",
    task_type: KIND_FIXED_KEY,
    agreed_price_micros: VIDEO_RENDER_PRICE_MICROS,
    provider_cost_limit_micros: VIDEO_RENDER_CEILING_MICROS,
    total_provider_cost_micros: 2_870_000,
    event_count: 41,
    created_at: "2026-08-30T11:20:00Z",
    completed_at: "2026-08-30T11:31:00Z",
  }),
  run({
    task_id: "d4e8b2a6-7c15-4f39-9a02-3b6e8d1c5f27",
    task_type: KIND_EVENT_PRICED_KEY,
    total_provider_cost_micros: 310_000,
    total_billed_cost_micros: 620_000,
    event_count: 4,
    created_at: "2026-08-29T09:12:00Z",
    completed_at: "2026-08-29T09:13:00Z",
  }),
  run({
    task_id: "a1c6d9e3-5b28-4e47-8f60-9d2b7a4c1e58",
    task_type: KIND_FIXED_NEGOTIATED_KEY,
    agreed_price_micros: TRANSCRIPT_LOW_PRICE_MICROS,
    provider_cost_limit_micros: TRANSCRIPT_CEILING_MICROS,
    total_provider_cost_micros: 1_950_000,
    event_count: 22,
    created_at: "2026-08-28T16:00:00Z",
    completed_at: "2026-08-28T16:09:00Z",
  }),
  run({
    task_id: "f7b3e1c9-0a64-4d21-b8c5-6e4f2a9d3b70",
    task_type: KIND_FIXED_KEY,
    status: "failed",
    outcome_reason: "upstream_provider_error",
    agreed_price_micros: VIDEO_RENDER_PRICE_MICROS,
    provider_cost_limit_micros: VIDEO_RENDER_CEILING_MICROS,
    total_provider_cost_micros: 410_000,
    event_count: 3,
    created_at: "2026-08-27T08:30:00Z",
    completed_at: "2026-08-27T08:31:00Z",
  }),
  run({
    task_id: "2e9a7c4b-6d03-4f58-a1b7-8c5d0e3f6a12",
    task_type: KIND_EVENT_PRICED_KEY,
    total_provider_cost_micros: 275_000,
    total_billed_cost_micros: 550_000,
    event_count: 3,
    created_at: "2026-08-26T13:45:00Z",
    completed_at: "2026-08-26T13:46:00Z",
  }),
];
