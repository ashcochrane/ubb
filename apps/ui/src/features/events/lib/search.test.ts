import { describe, expect, it } from "vitest";

import { eventsSearchSchema, shortId } from "./search";

describe("eventsSearchSchema", () => {
  it("passes valid search state through unchanged", () => {
    const parsed = eventsSearchSchema.parse({
      customer_id: "7f3c2a10-9b4e-4c9a-8f21-6d5e8a301b42",
      past_limit: true,
      stop_scope: "customer",
      episode_seq: 3,
      group_by: "provider",
      tag_key: "env",
      tag_value: "prod",
      start_date: "2026-07-01",
      end_date: "2026-07-23",
    });
    expect(parsed.past_limit).toBe(true);
    expect(parsed.stop_scope).toBe("customer");
    expect(parsed.episode_seq).toBe(3);
    expect(parsed.group_by).toBe("provider");
  });

  it("catches mangled values instead of crashing the route", () => {
    const parsed = eventsSearchSchema.parse({
      past_limit: "yes",
      stop_scope: "galaxy",
      episode_seq: -4,
      group_by: "nonsense",
      start_date: "not-a-date",
    });
    expect(parsed.past_limit).toBeUndefined();
    expect(parsed.stop_scope).toBeUndefined();
    expect(parsed.episode_seq).toBeUndefined();
    expect(parsed.group_by).toBeUndefined();
    expect(parsed.start_date).toBeUndefined();
  });
});

describe("shortId", () => {
  it("shortens UUIDs to their first 8 characters", () => {
    expect(shortId("7f3c2a10-9b4e-4c9a-8f21-6d5e8a301b42")).toBe("7f3c2a10…");
  });
});
