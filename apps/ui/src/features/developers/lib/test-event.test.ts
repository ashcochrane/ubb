import { describe, expect, it } from "vitest";

import {
  buildTestEventRequest,
  sandboxResetCurl,
  shortenUuid,
  testEventFormSchema,
  toMicros,
  type TestEventFormValues,
} from "./test-event";

const BASE_VALUES: TestEventFormValues = {
  customer_id: "c1a2b3d4-0001-4abc-9def-000000000001",
  event_type: "",
  provider: "",
  product_id: "",
  units: "",
  provider_cost: "",
  billed_cost: "",
  effective_at: "",
  idempotency_key: "idem-1",
  metrics: [{ key: "", value: "" }],
};

describe("toMicros", () => {
  it("converts currency units to integer micros", () => {
    expect(toMicros("1")).toBe(1_000_000);
    expect(toMicros("0.42")).toBe(420_000);
    // Rounds instead of truncating float noise.
    expect(toMicros("0.1")).toBe(100_000);
    expect(toMicros("1.000001")).toBe(1_000_001);
  });
});

describe("buildTestEventRequest", () => {
  it("includes only the required trio when optionals are empty", () => {
    const body = buildTestEventRequest(BASE_VALUES, "console-req-1");
    expect(body).toEqual({
      customer_id: BASE_VALUES.customer_id,
      request_id: "console-req-1",
      idempotency_key: "idem-1",
    });
  });

  it("converts costs to micros and assembles usage_metrics", () => {
    const body = buildTestEventRequest(
      {
        ...BASE_VALUES,
        event_type: "chat_completion",
        units: "3",
        provider_cost: "0.42",
        billed_cost: "0.6",
        metrics: [
          { key: "tokens_in", value: "1200" },
          { key: "", value: "" },
        ],
      },
      "console-req-2",
    );
    expect(body.event_type).toBe("chat_completion");
    expect(body.units).toBe(3);
    expect(body.provider_cost_micros).toBe(420_000);
    expect(body.billed_cost_micros).toBe(600_000);
    expect(body.usage_metrics).toEqual({ tokens_in: 1200 });
  });

  it("sends effective_at as a tz-aware UTC ISO string", () => {
    const body = buildTestEventRequest(
      { ...BASE_VALUES, effective_at: "2026-07-20T10:30" },
      "console-req-3",
    );
    // datetime-local values are naive; the builder converts to UTC "Z" form
    // because the API rejects naive timestamps.
    expect(body.effective_at).toMatch(/Z$/);
    expect(new Date(body.effective_at ?? "").getTime()).toBe(
      new Date("2026-07-20T10:30").getTime(),
    );
  });
});

describe("testEventFormSchema", () => {
  it("rejects a non-UUID customer id and a fractional metric quantity", () => {
    const result = testEventFormSchema.safeParse({
      ...BASE_VALUES,
      customer_id: "not-a-uuid",
      metrics: [{ key: "tokens_in", value: "1.5" }],
    });
    expect(result.success).toBe(false);
    const paths = result.success
      ? []
      : result.error.issues.map((issue) => issue.path.join("."));
    expect(paths).toContain("customer_id");
    expect(paths).toContain("metrics.0.value");
  });

  it("accepts a fully-empty optional surface", () => {
    expect(testEventFormSchema.safeParse(BASE_VALUES).success).toBe(true);
  });
});

describe("copy helpers", () => {
  it("builds a sandbox-key reset curl with keep_config", () => {
    const curl = sandboxResetCurl("https://api.example.com");
    expect(curl).toContain("https://api.example.com/api/v1/sandbox/reset");
    expect(curl).toContain("ubb_test_YOUR_SANDBOX_KEY");
    expect(curl).toContain('"keep_config": true');
  });

  it("shortens UUIDs for pickers", () => {
    expect(shortenUuid("c1a2b3d4-0001-4abc-9def-000000000001")).toBe("c1a2b3d4…");
  });
});
