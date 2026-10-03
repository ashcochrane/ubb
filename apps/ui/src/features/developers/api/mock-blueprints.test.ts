import { afterEach, describe, expect, it } from "vitest";

import { ApiProblem } from "@/api/problem";
import { setMockMemberRole } from "@/hooks/use-current-role";

import {
  BLUEPRINT_FIXTURE_NAMES,
  loadBlueprintFixture,
  mockAnswers,
  mockRegistry,
  resetMockConfiguration,
  reviseMockConfiguration,
  selectionAnsweredBy,
  selectionKey,
  THE_REVISION,
} from "./mock-blueprints";
import { resolveBlueprint } from "./mock";

afterEach(() => {
  resetMockConfiguration();
  setMockMemberRole("admin");
});

describe("the platform-written Blueprints the mock answers with", () => {
  it("are every fixture the platform wrote, each a Blueprint", async () => {
    // A vacuity guard as much as a check: a glob that matched nothing would
    // leave every other case here passing over an empty set.
    expect(BLUEPRINT_FIXTURE_NAMES.length).toBeGreaterThanOrEqual(19);
    for (const name of BLUEPRINT_FIXTURE_NAMES) {
      await expect(loadBlueprintFixture(name)).resolves.toBeTruthy();
    }
  });

  it("answer each selection with the Blueprint the platform wrote for it", async () => {
    const answers = await mockAnswers();
    for (const name of BLUEPRINT_FIXTURE_NAMES) {
      if (name === THE_REVISION.after) continue;
      const blueprint = await loadBlueprintFixture(name);

      expect(answers.get(selectionKey(selectionAnsweredBy(blueprint)))).toEqual(blueprint);
    }
  });

  it("never give two answers to one selection, before the revision or after it", async () => {
    await expect(mockAnswers()).resolves.toBeInstanceOf(Map);
    reviseMockConfiguration();
    await expect(mockAnswers()).resolves.toBeInstanceOf(Map);
  });
});

describe("the mock tenant's one configuration change", () => {
  const SELECTION = {
    target: "shell_http" as const,
    task_type: "report_generation",
    event_types: [THE_REVISION.eventType],
    subtask_types: [],
    draft_preview: false,
  };

  it("answers the blocked Blueprint before it and the complete one after it", async () => {
    const before = await resolveBlueprint(SELECTION);
    reviseMockConfiguration();
    const after = await resolveBlueprint(SELECTION);

    expect(before).toEqual(await loadBlueprintFixture(THE_REVISION.before));
    expect(before.readiness).toBe("blocked");
    expect(after).toEqual(await loadBlueprintFixture(THE_REVISION.after));
    expect(after.readiness).toBe("complete");
    expect(after.configuration_fingerprint).not.toBe(before.configuration_fingerprint);
  });

  it("answers nothing else naming the revised Event Type afterwards", async () => {
    reviseMockConfiguration();

    await expect(resolveBlueprint({ ...SELECTION, target: "python_sdk" })).rejects.toMatchObject({
      code: "mock_has_no_blueprint",
    });
  });
});

describe("the mock's server", () => {
  it("refuses a draft preview below the admin role, as the route does", async () => {
    setMockMemberRole("write");

    const refusal = await resolveBlueprint({
      target: "python_sdk",
      task_type: "report_generation",
      event_types: ["chat.completion"],
      subtask_types: [],
      draft_preview: true,
    }).catch((error: unknown) => error);

    expect(refusal).toBeInstanceOf(ApiProblem);
    expect(refusal).toMatchObject({ status: 403, code: "forbidden" });
  });

  it("answers a draft preview for an admin, with no fingerprint", async () => {
    const draft = await resolveBlueprint({
      target: "python_sdk",
      task_type: "report_generation",
      event_types: ["chat.completion"],
      subtask_types: [],
      draft_preview: true,
    });

    expect(draft.configuration_fingerprint).toBeNull();
  });

  it("says so where the platform wrote no Blueprint for a selection", async () => {
    await expect(
      resolveBlueprint({
        target: "python_sdk",
        task_type: "nowhere",
        event_types: [],
        subtask_types: [],
        draft_preview: false,
      }),
    ).rejects.toMatchObject({ status: 404, code: "mock_has_no_blueprint" });
  });
});

describe("what Configure offers in mock mode", () => {
  it("is every kind the answered Blueprints start, at the altitude they start it", async () => {
    const { kinds } = await mockRegistry();
    const altitude = Object.fromEntries(kinds.map((kind) => [kind.key, kind.kind]));

    expect(altitude).toMatchObject({ report_generation: "task", summarise: "subtask" });
  });

  it("is every Event Type they record, a draft one as a draft", async () => {
    const { eventTypes } = await mockRegistry();
    const status = Object.fromEntries(eventTypes.map((row) => [row.key, row.declaration_status]));

    expect(status).toMatchObject({ "chat.completion": "published", "draft.only": "draft" });
  });
});
