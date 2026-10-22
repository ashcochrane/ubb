// The contract's first discriminated union, through the console's typed client
// (#553, ADR-0021 §1).
//
// The publish act's change body is one of two bodies told apart by `line`, and
// a diff row answers the same union back. What this file proves is that the
// generated types carry the union as a union — a body of each variant compiles,
// a body naming neither does not, and a diff row exposes only what its own
// variant carries until it is narrowed. `tsc -b` is half of the assertion: the
// `@ts-expect-error` lines below fail the typecheck the day the generated
// types stop refusing what they refuse.

import { describe, expect, it } from "vitest";

import type { BookChangeDiff, BookChangeIn, BookPublishIn } from "./types";

const A_RATE_CHANGE: BookChangeIn = {
  line: "rate",
  kind: "reprice",
  measurement_key: "input_tokens",
  provider: "",
  event_type: "",
  task_type: "",
  subtask_type: "",
  grouping_fields: {},
  rate_per_unit_micros: 2,
};

const AN_AGREED_PRICE_CHANGE: BookChangeIn = {
  line: "agreed_price",
  kind: "add",
  task_type: "transcode",
  agreed_price_micros: 8_000_000,
};

// @ts-expect-error — a change names which kind of line it is about.
const NAMES_NO_LINE: BookChangeIn = { kind: "add", task_type: "transcode" };

const A_PRICE_WITH_A_QUANTITY: BookChangeIn = {
  line: "agreed_price",
  kind: "add",
  task_type: "transcode",
  // @ts-expect-error — an agreed price carries no quantity.
  measurement_key: "input_tokens",
};

/** What a row says, read through the narrowing a screen has to do. */
function describeRow(row: BookChangeDiff): string {
  if (row.line === "agreed_price") {
    // @ts-expect-error — an agreed price's row names no quantity.
    void row.measurement_key;
    return `${row.task_type}: ${row.after?.agreed_price_micros ?? "none"}`;
  }
  return `${row.measurement_key}: ${row.after?.rate_per_unit_micros ?? "none"}`;
}

describe("a book change names its line", () => {
  it("carries both bodies in one publish", () => {
    const body: BookPublishIn = { changes: [A_RATE_CHANGE, AN_AGREED_PRICE_CHANGE] };

    expect(body.changes.map((change) => change.line)).toEqual(["rate", "agreed_price"]);
    expect([NAMES_NO_LINE, A_PRICE_WITH_A_QUANTITY]).toHaveLength(2);
  });

  it("narrows a diff row on its line before reading what only it carries", () => {
    expect(
      describeRow({
        line: "agreed_price",
        kind: "add",
        task_type: "transcode",
        before: null,
        after: { agreed_price_micros: 8_000_000 },
      }),
    ).toBe("transcode: 8000000");
    expect(
      describeRow({
        line: "rate",
        kind: "retire",
        measurement_key: "input_tokens",
        provider: "",
        event_type: "",
        task_type: "",
        subtask_type: "",
        grouping_fields: {},
        before: null,
        after: null,
      }),
    ).toBe("input_tokens: none");
  });
});
