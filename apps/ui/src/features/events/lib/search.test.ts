import { describe, expect, it } from "vitest";

import { eventsSearchSchema, shortId } from "./search";

describe("eventsSearchSchema", () => {
  it("passes valid search state through unchanged", () => {
    const parsed = eventsSearchSchema.parse({
      customer_id: "7f3c2a10-9b4e-4c9a-8f21-6d5e8a301b42",
      past_limit: true,
      stop_scope: "customer",
      episode_seq: 3,
      group_by: "field:provider",
      tag_key: "env",
      tag_value: "prod",
      start_date: "2026-07-01",
      end_date: "2026-07-23",
    });
    expect(parsed.past_limit).toBe(true);
    expect(parsed.stop_scope).toBe("customer");
    expect(parsed.episode_seq).toBe(3);
    expect(parsed.group_by).toBe("field:provider");
  });

  it("keeps a rollup axis, which is as legal a group-by as a field", () => {
    // The two kinds share one parameter (§6), so a schema that only ever let
    // `field:` through would silently drop half the vocabulary — and drop it
    // the way this one drops nonsense, with no error anywhere.
    const parsed = eventsSearchSchema.parse({ group_by: "rollup:event_category" });

    expect(parsed.group_by).toBe("rollup:event_category");
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

  it("drops a bookmark carrying the retired shape rather than forwarding it", () => {
    // A URL saved before #506 named the axis with no kind, because the call
    // site prefixed it. Left alone it would reach the server as an axis word
    // that names nothing, and the chart would render a refusal for a link that
    // used to work — so it resolves to "no grouping" instead.
    const parsed = eventsSearchSchema.parse({ group_by: "provider" });

    expect(parsed.group_by).toBeUndefined();
  });
});

describe("shortId", () => {
  it("shortens UUIDs to their first 8 characters", () => {
    expect(shortId("7f3c2a10-9b4e-4c9a-8f21-6d5e8a301b42")).toBe("7f3c2a10…");
  });
});
