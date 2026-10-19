// A stop's two figures are read off a Verify answer's TEXT, and never as the
// number `JSON.parse` makes of them (#585; the owner's check on #613).
//
// The platform keeps both in a signed 64-bit money column and its contract
// types them `integer` with no narrower bound, so a legal figure can run past
// 2^53, where a number stops holding an integer exactly. These tests hold the
// read at the extremes of that column, on both paths an answer reaches the
// page by: the API client, asked for the body as text, and the mock's
// platform-written answers.

import { afterEach, describe, expect, it, vi } from "vitest";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock("@/api/client", () => ({ rootApi: { POST: post }, tenantApi: {} }));

import { verifyBlueprint } from "./api";
import { readWithExactFigures, verificationFromText, withNumbersAsText } from "./exact-figures";
import { loadVerificationFixture, VERIFICATION_FIXTURE_NAMES } from "./mock-verifications";

/** An answer as the platform could write it: a stop at the extremes, and a
 * grouping value that spells a figure inside a string. */
const ANSWER = `{
  "configuration_fingerprint": "f",
  "records": [
    {
      "event_type": "chat.completion",
      "acknowledgement": {
        "event_id": "e1", "stop": true, "stop_reason": "hard_floor", "stop_scope": "customer",
        "trigger_source": "usage_ingest",
        "stop_bound_micros": -9223372036854775807,
        "stop_measured_micros": -9223372036854775808,
        "grouping_fields": {"note": "\\"stop_bound_micros\\": 1, \\\\\\" ,"},
        "provider_cost_micros": 3000000
      },
      "replay": {
        "event_id": "e1", "stop": true, "stop_reason": "task_cogs_ceiling", "stop_scope": "task",
        "trigger_source": "usage_ingest",
        "stop_bound_micros": 9007199254740993,
        "stop_measured_micros": 9223372036854775807
      }
    },
    {
      "event_type": "search.run",
      "acknowledgement": {
        "event_id": "e2", "stop": false, "trigger_source": null,
        "stop_bound_micros": null, "stop_measured_micros": null
      },
      "replay": null
    }
  ]
}`;

afterEach(() => post.mockReset());

describe("reading a stop's figures off an answer's text", () => {
  it("carries every digit at the extremes of a signed 64-bit amount, where JSON.parse rounds", () => {
    const read = verificationFromText(ANSWER);

    expect(read.records[0]?.acknowledgement?.stop_bound_micros).toBe("-9223372036854775807");
    expect(read.records[0]?.acknowledgement?.stop_measured_micros).toBe("-9223372036854775808");
    expect(read.records[0]?.replay?.stop_bound_micros).toBe("9007199254740993");
    expect(read.records[0]?.replay?.stop_measured_micros).toBe("9223372036854775807");
    // What it would have been: a number, which cannot hold these.
    const parsed = JSON.parse(ANSWER) as { records: { replay: { stop_bound_micros: number } }[] };
    expect(String(parsed.records[0]?.replay.stop_bound_micros)).toBe("9007199254740992");
  });

  it("keeps a null a null, and every other number the number it is", () => {
    const read = verificationFromText(ANSWER);

    expect(read.records[1]?.acknowledgement?.stop_bound_micros).toBeNull();
    expect(read.records[1]?.acknowledgement?.stop_measured_micros).toBeNull();
    expect(read.records[0]?.acknowledgement?.provider_cost_micros).toBe(3_000_000);
    // A string that spells a figure is a string, never read for one.
    expect(read.records[0]?.acknowledgement?.grouping_fields).toEqual({
      note: '"stop_bound_micros": 1, \\" ,',
    });
  });

  // As the generated shell file refuses one (ADR-0017 §4): a figure the
  // contract types `integer` and the platform did not write as one is a broken
  // answer, never a figure to round, fill in or drop.
  it.each(["5000000.0", "6e6", '"5000000"', "true", "{}"])(
    "refuses a figure written %s, rather than round it, fill it or drop it",
    (written) => {
      const text = `{"records":[{"acknowledgement":{"stop_bound_micros":${written},"stop_measured_micros":1}}]}`;

      expect(() => readWithExactFigures(text)).toThrow(/stop_bound_micros is not a whole number of micros/);
    },
  );

  it("writes every number outside a string as its own text, and nothing else", () => {
    expect(withNumbersAsText('{"a": -1.5e3, "b": [0, 12], "c": "-1 \\" 2", "d": null}')).toBe(
      '{"a": "-1.5e3", "b": ["0", "12"], "c": "-1 \\" 2", "d": null}',
    );
  });
});

describe("the API client's answer", () => {
  it("is asked for as text, and its figures are the digits the platform wrote", async () => {
    post.mockResolvedValue({ data: ANSWER, response: new Response(null, { status: 200 }) });

    const answer = await verifyBlueprint("f", { records: [{ event_type: "chat.completion" }] });

    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0]?.[1]).toMatchObject({ parseAs: "text" });
    expect(answer.records[0]?.acknowledgement?.stop_measured_micros).toBe("-9223372036854775808");
    expect(answer.records[0]?.replay?.stop_measured_micros).toBe("9223372036854775807");
  });
});

describe("the mock's platform-written answers", () => {
  // Every committed answer is read the same way, and its figures pass the
  // type guard as digits or null — a number would not.
  it("reads every answer with its figures as digits or null", async () => {
    expect(VERIFICATION_FIXTURE_NAMES.length).toBeGreaterThan(0);
    for (const name of VERIFICATION_FIXTURE_NAMES) {
      const committed = await loadVerificationFixture(name);
      if (committed.kind !== "answered") continue;
      for (const record of committed.answer.records) {
        for (const acknowledgement of [record.acknowledgement, record.replay]) {
          if (acknowledgement == null) continue;
          for (const figure of [acknowledgement.stop_bound_micros, acknowledgement.stop_measured_micros]) {
            expect(figure === null || typeof figure === "string", name).toBe(true);
          }
        }
      }
    }
  });
});
