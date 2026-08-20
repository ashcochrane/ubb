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
  provider_cost: "",
  effective_at: "",
  idempotency_key: "idem-1",
  measurements: [{ key: "", value: "" }],
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

  it("converts the supplier cost to micros and assembles measurements", () => {
    const body = buildTestEventRequest(
      {
        ...BASE_VALUES,
        event_type: "chat_completion",
        provider_cost: "0.42",
        measurements: [
          { key: "tokens_in", value: "1200" },
          { key: "", value: "" },
        ],
      },
      "console-req-2",
    );
    expect(body.event_type).toBe("chat_completion");
    expect(body.provider_cost_micros).toBe(420_000);
    expect(body.measurements).toEqual({ tokens_in: 1200 });
  });

  it("sends no customer price, on a body with every field filled in", () => {
    // ⚠ THE WHOLE BODY, NOT A KEY AT A TIME, and this is the shape that would
    // hide it: every optional filled in, so an extra key rides along beside
    // seven legitimate ones. The API deleted `billed_cost_micros` and REFUSES a
    // body carrying it (#365) — unlike every other retired key, which it drops
    // — so a builder that still emitted one would 422 this whole panel.
    const body = buildTestEventRequest(
      {
        ...BASE_VALUES,
        event_type: "chat_completion",
        provider: "anthropic",
        product_id: "assistant-pro",
        provider_cost: "0.42",
        effective_at: "2026-07-20T10:30",
        measurements: [{ key: "tokens_in", value: "1200" }],
      },
      "console-req-4",
    );
    expect(Object.keys(body).sort()).toEqual([
      "customer_id",
      "effective_at",
      "event_type",
      "idempotency_key",
      "measurements",
      "product_id",
      "provider",
      "provider_cost_micros",
      "request_id",
    ]);
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
  it("rejects a non-UUID customer id and a fractional measurement quantity", () => {
    const result = testEventFormSchema.safeParse({
      ...BASE_VALUES,
      customer_id: "not-a-uuid",
      measurements: [{ key: "tokens_in", value: "1.5" }],
    });
    expect(result.success).toBe(false);
    const paths = result.success
      ? []
      : result.error.issues.map((issue) => issue.path.join("."));
    expect(paths).toContain("customer_id");
    expect(paths).toContain("measurements.0.value");
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
