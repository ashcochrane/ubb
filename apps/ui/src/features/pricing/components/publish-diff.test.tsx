// A draft's diff, rendered from a fixture THIS FILE builds (spec §25).
//
// ⚠ WHY A SECOND FILE, AND WHY THE PROVIDER IS STUBBED. Spec §25: *"a rendering
// test cannot see a narrowing defect where the mock returns its fixture
// object. The mutation stays green across every component test."* Every other
// case in this feature renders what `features/pricing/api/mock.ts` composed —
// and that mock AUTHORS the diff: `diffFor` decides what `before` and `after`
// are for every draft the console sees. Narrow the renderer against a shape the
// mock never produces and nothing goes red, because nothing ever asked it to
// render one.
//
// ⚠ THE SHAPE NO MOCK-AUTHORED CASE PRODUCES IS A RETIRE, and the claim is
// exactly that rather than anything stronger. The mock CAN build one — the
// dialog stages a retire and `diffFor` returns `after: null` for it — but the
// seeded drafts are two reprices and an add, and no case drives the dialog into
// a retire. So `after: null` reaches the renderer here and nowhere else, which
// is what makes the mutation below discriminating; if a later commit stages a
// retire through the dialog, this comment stops being true and the measurement
// under it has to be re-taken.
//
// `after: null` is precisely where the classic `amount ?? 0` lives: a retire
// that rendered `$0.00` would tell a tenant their book now prices that usage at
// nothing, when what it does is stop pricing it at all. Those are opposite
// facts wearing the same empty cell.
//
// ⚠ THE MUTATION THAT PROVES IT IS NOT VACUOUS. In `publish-diff.tsx`, make
// `Terms` render `formatMicros(0, currency)` instead of `ABSENT_LABEL` when
// `terms` is null — the classic `?? 0`, written where a whole side of a change
// is absent rather than where an amount is.
//
// MEASURED ON THIS COMMIT: **2 of 510 fail, and both are in this file** —
// `renders a retire as an absence` and `renders an add with no before`. NOT ONE
// mock-authored component test moves: not the book page's diff cases, not the
// dialog's, because none of them has a null side to render. That is exactly the shape spec §25 describes, and it is
// a NARROWING rather than a rename: no token moves, a branch simply stops being
// reachable from anything the mock authors.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ABSENT_LABEL } from "@/lib/localisation";
import type { BookPublish, PricingBook } from "../api/types";
import { BookChangesPanel } from "./book-changes-panel";

const BOOK: PricingBook = {
  id: "book-under-test",
  key: "hand-built",
  name: "Hand-built book",
  version: 1,
  is_default: false,
  customer_id: null,
};

/**
 * One draft carrying all three acts, which is the point: a diff row is read as
 * a CHANGE rather than as an outcome, so the three read differently by shape
 * before they read differently by word.
 */
const DRAFT: BookPublish = {
  id: "publish-under-test",
  book_id: BOOK.id,
  declaration_status: "draft",
  effective_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
  actor_kind: "member",
  actor_id: "usr_test",
  actor_display: "dana@acme.ai",
  opened_rule_ids: [],
  closed_rule_ids: [],
  published_at: null,
  diff_unavailable_reason: null,
  diff: [
    {
      kind: "add",
      measurement_key: "audio_seconds",
      provider: "openai",
      event_type: "audio.transcription",
      task_type: "",
      subtask_type: "",
      grouping_fields: {},
      // Nothing priced this before, so there is no before.
      before: null,
      after: {
        rate_structure: "per_unit",
        rate_per_unit_micros: 6_000_000,
        unit_quantity: 1_000_000,
        fixed_micros: 0,
        pricing_method: "direct_event_price",
      },
    },
    {
      // ⚠ THE MONEY DOES NOT MOVE AND THE DEAL DOES. Same amount, same
      // denominator, different method — a rule going from a margin over cost
      // onto a flat price. A row that rendered only the amounts would read as
      // "nothing changed" for the one change that alters what the customer is
      // exposed to when their supplier's prices move.
      kind: "reprice",
      measurement_key: "gpt4o_input_tokens",
      provider: "openai",
      event_type: "chat.completion",
      task_type: "",
      subtask_type: "",
      grouping_fields: { model: "gpt-4o", tier: "premium" },
      before: {
        rate_structure: "per_unit",
        rate_per_unit_micros: 5_000_000,
        unit_quantity: 1_000_000,
        fixed_micros: 0,
        pricing_method: "margin_over_cost",
      },
      after: {
        rate_structure: "per_unit",
        rate_per_unit_micros: 5_000_000,
        unit_quantity: 1_000_000,
        fixed_micros: 0,
        pricing_method: "direct_event_price",
      },
    },
    {
      kind: "retire",
      measurement_key: "image_generation",
      provider: "openai",
      event_type: "image.generation",
      task_type: "",
      subtask_type: "",
      grouping_fields: {},
      before: {
        rate_structure: "fixed_component",
        rate_per_unit_micros: 0,
        unit_quantity: 1,
        fixed_micros: 90_000,
        pricing_method: "direct_event_price",
      },
      // A retire opens no rule. THE SHAPE THE MOCK NEVER PRODUCES.
      after: null,
    },
  ],
};

vi.mock("../api/provider", () => ({
  pricingApi: {
    // Only what this panel asks for. A stub that answered more would be a
    // second mock to keep true.
    listBookPublishes: async () => ({
      data: [DRAFT],
      has_more: false,
      next_cursor: null,
    }),
  },
}));

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <BookChangesPanel book={BOOK} />
    </QueryClientProvider>,
  );
}

function rowFor(measurementKey: string): HTMLElement {
  return screen.getByText(measurementKey).closest("li") as HTMLElement;
}

describe("a draft's diff", () => {
  it("renders a retire as an absence, never as a charge of nothing", async () => {
    renderPanel();
    expect(await screen.findByText("Retires")).toBeInTheDocument();

    const row = within(rowFor("image_generation"));
    // What it charges today is still shown — a tenant deciding whether to
    // retire a rule needs to see what they are giving up.
    expect(row.getByText("$0.09")).toBeInTheDocument();
    // And what it will charge afterwards is NOTHING AT ALL, which is not the
    // same as nothing.
    expect(row.getByText(ABSENT_LABEL)).toBeInTheDocument();
    expect(row.queryByText("$0.00")).not.toBeInTheDocument();
  });

  it("renders an add with no before, and no invented one", async () => {
    renderPanel();
    expect(await screen.findByText("Adds a rule")).toBeInTheDocument();

    const row = within(rowFor("audio_seconds"));
    expect(row.getByText("$6 / 1M")).toBeInTheDocument();
    expect(row.getByText(ABSENT_LABEL)).toBeInTheDocument();
    expect(row.queryByText("$0.00")).not.toBeInTheDocument();
  });

  // ⚠ THE CHANGE THAT IS INVISIBLE IN THE AMOUNTS. A tenant moving a rule from
  // a margin over cost onto a flat price has changed what their customer is
  // exposed to; the number is identical. This is the assertion that a diff
  // renders the METHOD rather than only the money.
  it("shows a change of method even where the amount does not move", async () => {
    renderPanel();
    expect(await screen.findByText("Reprices")).toBeInTheDocument();

    const row = within(rowFor("gpt4o_input_tokens"));
    expect(row.getAllByText("$5 / 1M")).toHaveLength(2);
    expect(row.getByText(/Margin over cost/)).toBeInTheDocument();
    expect(row.getByText(/Direct event price/)).toBeInTheDocument();
  });

  it("names what the changed rule pins, in the tenant's own words", async () => {
    renderPanel();
    expect(await screen.findByText("Reprices")).toBeInTheDocument();

    const row = within(rowFor("gpt4o_input_tokens"));
    expect(row.getByText("gpt-4o")).toBeInTheDocument();
    expect(row.getByText("premium")).toBeInTheDocument();
    // The tenant's declared key, never the slot number it happens to occupy.
    expect(row.getByText("tier=")).toBeInTheDocument();
    expect(row.queryByText(/grouping_field/)).not.toBeInTheDocument();
  });

  it("reads a dated change as scheduled, and says when", async () => {
    renderPanel();
    expect(await screen.findByText("Scheduled")).toBeInTheDocument();
    expect(screen.getByText(/This book changes on/)).toBeInTheDocument();
    expect(screen.getByText(/1 change is waiting, 1 of them dated ahead/i))
      .toBeInTheDocument();
  });
});
