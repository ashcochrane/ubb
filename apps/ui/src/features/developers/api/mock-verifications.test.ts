// The mock's Verify answers are the platform's own, and it answers nothing
// else (#581).

import { afterEach, describe, expect, it } from "vitest";

import { ApiProblem } from "@/api/problem";
import { setMockMemberRole } from "@/hooks/use-current-role";

import { verifyBlueprint } from "./mock";
import { BLUEPRINT_FIXTURE_NAMES, loadBlueprintFixture } from "./mock-blueprints";
import {
  isVerification,
  loadVerificationFixture,
  mockVerifications,
  VERIFICATION_FIXTURE_NAMES,
  verificationKey,
} from "./mock-verifications";
import type { BlueprintVerificationRequest } from "./types";

afterEach(() => setMockMemberRole("admin"));

async function rejection(promise: Promise<unknown>): Promise<ApiProblem> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiProblem) return error;
    throw error;
  }
  throw new Error("expected a refusal");
}

describe("the platform-written Verify answers", () => {
  it("are all here, and each is an answer or a refusal of the platform's", async () => {
    // A glob that matched nothing would let every test below pass over none.
    expect(VERIFICATION_FIXTURE_NAMES.length).toBeGreaterThanOrEqual(10);
    const loaded = await Promise.all(VERIFICATION_FIXTURE_NAMES.map(loadVerificationFixture));
    expect(new Set(loaded.map((fixture) => fixture.kind))).toEqual(new Set(["answered", "refused"]));
  });

  // The fingerprint is how the mock finds an answer, so each must be the one
  // the console holds for the committed Blueprint it names.
  it("each verified the fingerprint of the committed Blueprint it names", async () => {
    for (const name of VERIFICATION_FIXTURE_NAMES) {
      const fixture = await loadVerificationFixture(name);
      if (fixture.blueprint === null) continue;
      expect(BLUEPRINT_FIXTURE_NAMES).toContain(fixture.blueprint);
      const blueprint = await loadBlueprintFixture(fixture.blueprint);
      expect(fixture.fingerprint, name).toBe(blueprint.configuration_fingerprint);
      if (fixture.kind === "answered") expect(fixture.answer.configuration_fingerprint).toBe(fixture.fingerprint);
    }
  });

  it("are one answer per request", async () => {
    expect((await mockVerifications()).size).toBe(VERIFICATION_FIXTURE_NAMES.length);
  });

  it("refuses a file that is not an answer", async () => {
    const answer = await loadVerificationFixture("reported-cost");
    if (answer.kind !== "answered") throw new Error("reported-cost is an answer");
    const [record] = answer.answer.records;

    expect(isVerification(answer.answer)).toBe(true);
    expect(isVerification({ ...answer.answer, verified: "yes" })).toBe(false);
    expect(
      isVerification({
        ...answer.answer,
        records: [{ ...record, acknowledgement: { ...record?.acknowledgement, costing_status: "free" } }],
      }),
    ).toBe(false);
  });
});

describe("one spelling of a request", () => {
  const request: BlueprintVerificationRequest = {
    records: [{ event_type: "a.event", measurements: { b: 2, a: 1 } }, { event_type: "b.event" }],
    grouping_fields: { phase: "draft", environment: "staging" },
  };

  it("is the same whatever order a map is in, and whether an empty optional is sent", () => {
    const reordered: BlueprintVerificationRequest = {
      grouping_fields: { environment: "staging", phase: "draft" },
      records: [
        { event_type: "a.event", measurements: { a: 1, b: 2 }, provider_cost_micros: null, subtask_type: null },
        { event_type: "b.event", measurements: {} },
      ],
    };
    expect(verificationKey("sha256:x", reordered)).toBe(verificationKey("sha256:x", request));
  });

  it("differs for another fingerprint, another sample, or the records in another order", () => {
    const key = verificationKey("sha256:x", request);

    expect(verificationKey("sha256:y", request)).not.toBe(key);
    expect(
      verificationKey("sha256:x", { ...request, grouping_fields: { phase: "final", environment: "staging" } }),
    ).not.toBe(key);
    expect(verificationKey("sha256:x", { ...request, records: [...request.records].reverse() })).not.toBe(key);
  });
});

describe("the mock's Verify", () => {
  it("answers the exact request the platform verified with the platform's answer", async () => {
    const fixture = await loadVerificationFixture("reported-cost");
    if (fixture.kind !== "answered") throw new Error("reported-cost is an answer");

    expect(await verifyBlueprint(fixture.fingerprint, fixture.request)).toEqual(fixture.answer);
  });

  it("refuses as the platform refused, with the refusal's own members", async () => {
    const fixture = await loadVerificationFixture("event-type-not-available");

    const refused = await rejection(verifyBlueprint(fixture.fingerprint, fixture.request));
    expect(refused.status).toBe(422);
    expect(refused.code).toBe("event_type_not_available");
    expect(refused.extensions["event_types"]).toEqual(["draft.only"]);
  });

  it("answers any other request as one the platform never answered", async () => {
    const fixture = await loadVerificationFixture("reported-cost");
    const [record] = fixture.request.records;
    const other = { ...fixture.request, records: [{ ...record, event_type: "web.search", measurements: { searches: 4 } }] };

    const refused = await rejection(verifyBlueprint(fixture.fingerprint, other));
    expect(refused.code).toBe("mock_has_no_verification");
    expect(refused.title).toBe("Not in the mock");
  });

  it.each([["read"], [null]] as const)("enforces the write floor against a %s role", async (role) => {
    setMockMemberRole(role);
    const fixture = await loadVerificationFixture("reported-cost");

    const refused = await rejection(verifyBlueprint(fixture.fingerprint, fixture.request));
    expect(refused.status).toBe(403);
    expect(refused.code).toBe("forbidden");
  });

  it("lets a write member verify", async () => {
    setMockMemberRole("write");
    const fixture = await loadVerificationFixture("reported-cost");

    await expect(verifyBlueprint(fixture.fingerprint, fixture.request)).resolves.toMatchObject({ verified: true });
  });
});
