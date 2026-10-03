import { describe, expect, it } from "vitest";

import {
  CODE_BUILDER_SEARCH_KEYS,
  codeBuilderSearchSchema,
  DEFAULT_TARGET,
  selectionOf,
} from "./code-builder-search";

const FINGERPRINT = `sha256:${"ab".repeat(32)}`;

// A key-shaped value, assembled so this file is not itself a key-shaped
// literal for the Developers feature's sweep to find.
const A_KEY = ["ubb", "live", "Qm3xk9TzLp0aRw2s8Vn4Yh6Jd1Fc5Gb7"].join("_");
const A_TOKEN = ["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiJ4In0", "c2lnbmF0dXJl"].join(".");

/** The properties the committed contract publishes on one request schema. */
function publishedProperties(schemaName: string): string[] {
  const [document] = Object.values(
    import.meta.glob("/src/api/schema.json", { eager: true, import: "default" }),
  );
  let node: unknown = document;
  for (const key of ["components", "schemas", schemaName, "properties"]) {
    node = typeof node === "object" && node !== null ? Reflect.get(node, key) : undefined;
  }
  if (typeof node !== "object" || node === null) {
    throw new Error(`the committed contract publishes no ${schemaName}`);
  }
  return Object.keys(node);
}

describe("the Code Builder's URL", () => {
  it("carries every declared key through unchanged", () => {
    const parsed = codeBuilderSearchSchema.parse({
      target: "shell_http",
      task_type: "report-generation",
      event_types: ["chat.completion", "it's a $5 chat-completion"],
      subtask_types: ["summarise"],
      draft_preview: true,
      held: FINGERPRINT,
    });

    expect(parsed).toEqual({
      target: "shell_http",
      task_type: "report-generation",
      event_types: ["chat.completion", "it's a $5 chat-completion"],
      subtask_types: ["summarise"],
      draft_preview: true,
      held: FINGERPRINT,
    });
  });

  it("declares exactly the keys it parses", () => {
    const parsed = codeBuilderSearchSchema.parse({
      target: "python_sdk",
      task_type: "k",
      event_types: ["e"],
      subtask_types: ["s"],
      draft_preview: false,
      held: FINGERPRINT,
    });

    expect(Object.keys(parsed).sort()).toEqual([...CODE_BUILDER_SEARCH_KEYS].sort());
  });

  it("drops a key it does not declare rather than forwarding it", () => {
    const parsed = codeBuilderSearchSchema.parse({
      target: "python_sdk",
      api_key: "anything",
      customer_id: "c1a2b3d4-0001-4abc-9def-000000000001",
    });

    expect(parsed).toEqual({ target: "python_sdk" });
  });

  it("catches a malformed value instead of crashing the route", () => {
    const parsed = codeBuilderSearchSchema.parse({
      target: "typescript",
      task_type: "has spaces",
      event_types: "not-an-array-of-one",
      subtask_types: [42, "", "ok_kind"],
      draft_preview: "yes",
      held: "sha256:short",
    });

    // A bare string is one Event Type, which is how a hand-typed URL says one.
    expect(parsed).toEqual({
      event_types: ["not-an-array-of-one"],
      subtask_types: ["ok_kind"],
    });
  });

  it("keeps each selection a set, in one order", () => {
    const parsed = codeBuilderSearchSchema.parse({
      event_types: ["b", "a", "b"],
      subtask_types: ["z", "y", "z"],
    });

    expect(parsed.event_types).toEqual(["a", "b"]);
    expect(parsed.subtask_types).toEqual(["y", "z"]);
  });

  it("refuses more than the fifty of each the API takes", () => {
    const many = Array.from({ length: 51 }, (_, index) => `event.${String(index).padStart(2, "0")}`);
    const parsed = codeBuilderSearchSchema.parse({ event_types: many });

    expect(parsed.event_types).toBeUndefined();
  });

  it("lets no secret-shaped value in under any key", () => {
    const parsed = codeBuilderSearchSchema.parse({
      task_type: A_KEY,
      event_types: [A_KEY, `Authorization: Bearer ${A_KEY}`, A_TOKEN, "chat.completion"],
      subtask_types: [A_KEY],
      held: A_KEY,
    });

    expect(parsed).toEqual({ event_types: ["chat.completion"] });
    expect(JSON.stringify(parsed)).not.toContain(A_KEY);
    expect(JSON.stringify(parsed)).not.toContain(A_TOKEN);
  });
});

describe("the selection a URL asks for", () => {
  it("asks for the default target when the URL names none", () => {
    expect(selectionOf({})).toEqual({
      target: DEFAULT_TARGET,
      task_type: null,
      event_types: [],
      subtask_types: [],
      draft_preview: false,
    });
  });

  it("carries the URL's selections and never the held fingerprint", () => {
    const selection = selectionOf({
      target: "shell_http",
      task_type: "report_generation",
      event_types: ["chat.completion"],
      subtask_types: ["summarise"],
      draft_preview: true,
      held: FINGERPRINT,
    });

    expect(selection).toEqual({
      target: "shell_http",
      task_type: "report_generation",
      event_types: ["chat.completion"],
      subtask_types: ["summarise"],
      draft_preview: true,
    });
  });

  // ⚠ THE SERVER DROPS AN UNKNOWN BODY KEY SILENTLY (#505), so a field the
  // request does not publish would be sent, discarded and never noticed. Held
  // to the committed contract the console is built from, not to a list here.
  it("posts only fields the resolve request publishes", () => {
    const published = publishedProperties("IntegrationBlueprintSelectionIn");
    expect(published).toContain("target");
    const selection = selectionOf({
      target: "python_sdk",
      task_type: "k",
      event_types: ["e"],
      subtask_types: ["s"],
      draft_preview: true,
      held: FINGERPRINT,
    });

    for (const key of Object.keys(selection)) {
      expect(published).toContain(key);
    }
  });
});
