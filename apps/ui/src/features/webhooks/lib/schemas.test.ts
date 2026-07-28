import { describe, expect, it } from "vitest";

import { WEBHOOK_EVENT_TYPES } from "@/lib/labels";

import { groupedEventTypes } from "./event-groups";
import {
  createEndpointSchema,
  endpointUrlSchema,
  rotateSecretSchema,
  secretSchema,
  toEventTypesPayload,
} from "./schemas";
import { generateWebhookSecret, hostOf } from "./secret";

const VALID_SECRET = "a".repeat(32);

describe("endpointUrlSchema", () => {
  it("accepts a public https URL", () => {
    expect(endpointUrlSchema.safeParse("https://api.acme.dev/hooks").success).toBe(true);
  });

  it("rejects plain http and non-URLs", () => {
    expect(endpointUrlSchema.safeParse("http://api.acme.dev/hooks").success).toBe(false);
    expect(endpointUrlSchema.safeParse("not a url").success).toBe(false);
    expect(endpointUrlSchema.safeParse("").success).toBe(false);
  });

  it("rejects URLs over 500 characters", () => {
    const long = `https://api.acme.dev/${"x".repeat(500)}`;
    expect(endpointUrlSchema.safeParse(long).success).toBe(false);
  });
});

describe("secretSchema", () => {
  it("enforces the 32–255 character contract bounds", () => {
    expect(secretSchema.safeParse("a".repeat(31)).success).toBe(false);
    expect(secretSchema.safeParse("a".repeat(32)).success).toBe(true);
    expect(secretSchema.safeParse("a".repeat(255)).success).toBe(true);
    expect(secretSchema.safeParse("a".repeat(256)).success).toBe(false);
  });
});

describe("createEndpointSchema", () => {
  const base = {
    url: "https://api.acme.dev/hooks",
    secret: VALID_SECRET,
    isActive: true,
  };

  it("requires at least one event type unless subscribing to all", () => {
    expect(
      createEndpointSchema.safeParse({ ...base, allEvents: false, eventTypes: [] })
        .success,
    ).toBe(false);
    expect(
      createEndpointSchema.safeParse({ ...base, allEvents: true, eventTypes: [] })
        .success,
    ).toBe(true);
    expect(
      createEndpointSchema.safeParse({
        ...base,
        allEvents: false,
        eventTypes: ["usage.recorded"],
      }).success,
    ).toBe(true);
  });

  it("maps the all-events toggle to the '*' selector", () => {
    expect(toEventTypesPayload({ allEvents: true, eventTypes: ["stop.fired"] })).toEqual([
      "*",
    ]);
    expect(toEventTypesPayload({ allEvents: false, eventTypes: ["stop.fired"] })).toEqual(
      ["stop.fired"],
    );
  });
});

describe("rotateSecretSchema", () => {
  it("bounds overlap_hours to 1–168 whole hours", () => {
    const valid = { newSecret: VALID_SECRET };
    expect(rotateSecretSchema.safeParse({ ...valid, overlapHours: 24 }).success).toBe(
      true,
    );
    expect(rotateSecretSchema.safeParse({ ...valid, overlapHours: 0 }).success).toBe(
      false,
    );
    expect(rotateSecretSchema.safeParse({ ...valid, overlapHours: 169 }).success).toBe(
      false,
    );
    expect(rotateSecretSchema.safeParse({ ...valid, overlapHours: 1.5 }).success).toBe(
      false,
    );
  });
});

describe("generateWebhookSecret", () => {
  it("produces 48 lowercase hex characters, fresh each call", () => {
    const first = generateWebhookSecret();
    const second = generateWebhookSecret();
    expect(first).toMatch(/^[0-9a-f]{48}$/);
    expect(second).toMatch(/^[0-9a-f]{48}$/);
    expect(first).not.toBe(second);
  });
});

describe("groupedEventTypes", () => {
  it("groups the full catalog by prefix and never includes '*'", () => {
    const groups = groupedEventTypes();
    const values = groups.flatMap((group) => group.options.map((o) => o.value));
    expect(values).toHaveLength(WEBHOOK_EVENT_TYPES.length);
    expect(values).not.toContain("*");
    const billing = groups.find((group) => group.key === "billing");
    expect(billing?.label).toBe("Billing");
    expect(billing?.options.map((o) => o.label)).toContain("Balance low");
  });
});

describe("hostOf", () => {
  it("extracts the host and falls back to the raw value", () => {
    expect(hostOf("https://api.acme.dev/webhooks/ubb")).toBe("api.acme.dev");
    expect(hostOf("not a url")).toBe("not a url");
  });
});
