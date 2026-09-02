// Mock fixtures for the tasks feature — one coherent story, September 2026.
//
// Acme AI (the tenant) has declared nine kinds of work under eight words —
// one word names a kind at either altitude. Three are sold at one agreed
// price, and the runs beneath them are what lets the console show a
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
//   render-shot         subtask  fixed          the contained work under a
//                                               video-render run, sold the way
//                                               its parent is sold
//   legacy-ocr          task     event priced   retired
//   translate           BOTH altitudes share the word — two declarations

import type { KindOfWork, RunRow, TaskStatus } from "./types";

export const KIND_EVENT_PRICED_KEY = "document-summary";
export const KIND_FIXED_KEY = "video-render";
export const KIND_FIXED_NEGOTIATED_KEY = "transcript-cleanup";
export const KIND_FIXED_UNSOLD_KEY = "image-upscale";
export const KIND_STEP_KEY = "render-frame";
export const KIND_FIXED_CONTAINED_KEY = "render-shot";
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
    key: KIND_FIXED_CONTAINED_KEY,
    kind: "subtask",
    pricing_mode: "fixed",
    default_provider_cost_limit_micros: 200_000,
    silence_window_seconds: 120,
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

// --- Runs ------------------------------------------------------------------
//
// The runs beneath those kinds tell the second story, the one the runs surface
// renders (#424): every lifecycle state at least once, and every reading a
// total can have — a figure, a floor, nothing UBB knows, and nothing that
// applies. Newest first, which is the order the route answers in.
//
//   6e1f2c8a  video-render        active     28 pieces of contained work, one of
//                                            them costed by nobody yet, so the
//                                            run's own total is a FLOOR
//   0b7d4e29  transcript-cleanup  completed  quoted $8.00 by the customer's book
//   3f0c9d2e  translate           completed  three events, none costed and none
//                                            priced: both totals UNKNOWN
//   9c3a5f71  video-render        completed  delivered at $5.00
//   7a2e5b1c  document-summary    expired    nobody said how it ended — NOT a
//                                            failure
//   d4e8b2a6  document-summary    completed  two pieces of contained work under
//                                            an event-priced run
//   4d7b1e9f  document-summary    killed     UBB stopped it past its ceiling;
//                                            two events still uncosted
//   a1c6d9e3  transcript-cleanup  completed  quoted $4.00
//   b8e2f4a1  translate           cancelled  withdrawn before anything ran: a
//                                            REAL zero
//   f7b3e1c9  video-render        failed     the caller said why
//   2e9a7c4b  document-summary    completed

export const RUN_ACTIVE_ID = "6e1f2c8a-3b47-4d90-a5e2-7c9d0b1f3a64";
export const RUN_UNKNOWN_COST_ID = "3f0c9d2e-5a71-4b38-9c46-1d8e7f2a6b03";
export const RUN_DELIVERED_FIXED_ID = "9c3a5f71-2d86-4b04-8e19-5a7c1d0e2f95";
export const RUN_EXPIRED_ID = "7a2e5b1c-9d40-4f67-8b23-6c1a3e5d9f48";
export const RUN_DELIVERED_EVENT_PRICED_ID = "d4e8b2a6-7c15-4f39-9a02-3b6e8d1c5f27";
export const RUN_KILLED_ID = "4d7b1e9f-2c58-4a06-b371-9e5f0d8c2a17";
export const RUN_CANCELLED_ID = "b8e2f4a1-6d93-4c25-a70e-3f1b9c8d5e62";
export const RUN_FAILED_ID = "f7b3e1c9-0a64-4d21-b8c5-6e4f2a9d3b70";

/**
 * How many pieces of contained work the active `video-render` run holds —
 * past the table's inline bound on purpose, so the fold is exercised against
 * a real page and not only in a component test.
 */
export const CONTAINED_UNDER_ACTIVE_RUN = 28;

/** Top-level runs, newest first — the order the route answers in. */
export const MOCK_RUNS: readonly RunRow[] = [
  run({
    task_id: RUN_ACTIVE_ID,
    task_type: KIND_FIXED_KEY,
    status: "active",
    agreed_price_micros: VIDEO_RENDER_PRICE_MICROS,
    provider_cost_limit_micros: VIDEO_RENDER_CEILING_MICROS,
    // Everything contained in it (1,197,000 over 28 events, one of them never
    // costed) plus 43,000 over two events reported against the run itself.
    total_provider_cost_micros: 1_240_000,
    unresolved_event_count: 1,
    event_count: 30,
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
    task_id: RUN_UNKNOWN_COST_ID,
    task_type: KIND_SHARED_WORD_KEY,
    total_provider_cost_micros: 0,
    unresolved_event_count: 3,
    total_billed_cost_micros: 0,
    unpriced_event_count: 3,
    event_count: 3,
    created_at: "2026-08-31T09:00:00Z",
    completed_at: "2026-08-31T09:04:00Z",
  }),
  run({
    task_id: RUN_DELIVERED_FIXED_ID,
    task_type: KIND_FIXED_KEY,
    agreed_price_micros: VIDEO_RENDER_PRICE_MICROS,
    provider_cost_limit_micros: VIDEO_RENDER_CEILING_MICROS,
    total_provider_cost_micros: 2_870_000,
    event_count: 41,
    created_at: "2026-08-30T11:20:00Z",
    completed_at: "2026-08-30T11:31:00Z",
  }),
  run({
    task_id: RUN_EXPIRED_ID,
    task_type: KIND_EVENT_PRICED_KEY,
    status: "expired",
    total_provider_cost_micros: 95_000,
    total_billed_cost_micros: 190_000,
    event_count: 2,
    created_at: "2026-08-30T02:00:00Z",
    completed_at: "2026-08-30T02:12:00Z",
  }),
  run({
    task_id: RUN_DELIVERED_EVENT_PRICED_ID,
    task_type: KIND_EVENT_PRICED_KEY,
    // Two pieces of contained work (175,000 / 350,000 over three events) plus
    // one event reported against the run itself.
    total_provider_cost_micros: 310_000,
    total_billed_cost_micros: 620_000,
    event_count: 4,
    created_at: "2026-08-29T09:12:00Z",
    completed_at: "2026-08-29T09:13:00Z",
  }),
  run({
    task_id: RUN_KILLED_ID,
    task_type: KIND_EVENT_PRICED_KEY,
    status: "killed",
    // A lower ceiling than the kind's, asked for at start, and crossed.
    provider_cost_limit_micros: 800_000,
    total_provider_cost_micros: 900_000,
    unresolved_event_count: 2,
    total_billed_cost_micros: 1_500_000,
    event_count: 9,
    created_at: "2026-08-28T20:00:00Z",
    completed_at: "2026-08-28T20:03:00Z",
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
    task_id: RUN_CANCELLED_ID,
    task_type: KIND_SHARED_WORD_KEY,
    status: "cancelled",
    outcome_reason: "customer_cancelled",
    reason_detail: "Closed before any work ran",
    created_at: "2026-08-27T15:00:00Z",
    completed_at: "2026-08-27T15:00:40Z",
  }),
  run({
    task_id: RUN_FAILED_ID,
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

function containedId(ordinal: number): string {
  return `c0000000-0000-4000-8000-${String(ordinal).padStart(12, "0")}`;
}

/**
 * The work contained in the active `video-render` run, oldest first — the
 * order the detail route answers in. Sold the way the run containing it is
 * sold (contained work shares its parent's regime), so every piece is under
 * `render-shot`, the fixed-regime contained kind. Every state a piece of
 * contained work can be in appears at least once, and one piece's cost was
 * never learned, so the roll-up is a floor rather than a figure.
 */
const CONTAINED_UNDER_ACTIVE: readonly RunRow[] = Array.from(
  { length: CONTAINED_UNDER_ACTIVE_RUN },
  (_, index) => {
    const ordinal = index + 1;
    const status: TaskStatus =
      ordinal === 3 ? "failed" : ordinal === 11 ? "expired" : ordinal >= 26 ? "active" : "completed";
    const uncosted = ordinal === 7;
    const startedAt = new Date(Date.UTC(2026, 8, 1, 14, 5 + ordinal)).toISOString();
    const endedAt = new Date(Date.UTC(2026, 8, 1, 14, 5 + ordinal, 40)).toISOString();
    return run({
      task_id: containedId(ordinal),
      parent_task_id: RUN_ACTIVE_ID,
      task_type: KIND_FIXED_CONTAINED_KEY,
      status,
      ...(status === "failed"
        ? { outcome_reason: "upstream_provider_error" as const, reason_detail: "Renderer answered 502" }
        : {}),
      total_provider_cost_micros: uncosted ? 0 : ordinal * 3_000,
      unresolved_event_count: uncosted ? 1 : 0,
      event_count: 1,
      created_at: startedAt,
      ...(status === "active" ? {} : { completed_at: endedAt }),
    });
  },
);

/** Two pieces of contained work under an event-priced run, each priced per event. */
const CONTAINED_UNDER_EVENT_PRICED: readonly RunRow[] = [
  run({
    task_id: "e5a1c7d3-4b29-4f86-9d05-7c3e1a8b2f60",
    parent_task_id: RUN_DELIVERED_EVENT_PRICED_ID,
    task_type: KIND_SHARED_WORD_KEY,
    total_provider_cost_micros: 100_000,
    total_billed_cost_micros: 200_000,
    event_count: 2,
    created_at: "2026-08-29T09:12:10Z",
    completed_at: "2026-08-29T09:12:40Z",
  }),
  run({
    task_id: "f2b8d4e6-1c57-4a93-8e20-5d9f3b7c1a84",
    parent_task_id: RUN_DELIVERED_EVENT_PRICED_ID,
    task_type: KIND_SHARED_WORD_KEY,
    total_provider_cost_micros: 75_000,
    total_billed_cost_micros: 150_000,
    event_count: 1,
    created_at: "2026-08-29T09:12:45Z",
    completed_at: "2026-08-29T09:12:58Z",
  }),
];

/**
 * What each run contains, by the run's id — the whole list per run, as
 * `GET /tasks/{id}` answers it. A run absent here contains nothing.
 */
export const MOCK_CONTAINED: Readonly<Record<string, readonly RunRow[]>> = {
  [RUN_ACTIVE_ID]: CONTAINED_UNDER_ACTIVE,
  [RUN_DELIVERED_EVENT_PRICED_ID]: CONTAINED_UNDER_EVENT_PRICED,
};
