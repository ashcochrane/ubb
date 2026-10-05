import { describe, expect, it } from "vitest";

import { loadBlueprintFixture } from "../api/mock-blueprints";
import { artifactOf, downloadName, FILE_KIND_TITLES, previewsByCall } from "./artifact";

async function filesOf(name: string) {
  const blueprint = await loadBlueprintFixture(name);
  const artifact = artifactOf(blueprint);
  if (artifact.kind !== "files") throw new Error(`${name} was refused: ${artifact.reason}`);
  return { blueprint, files: artifact.files };
}

describe("the artifact a Blueprint renders to", () => {
  it("is the module, the call sites, the environment example and the verify script for Python", async () => {
    const { files } = await filesOf("calculated-cost");
    const kinds = new Set(files.map((file) => file.kind));

    expect(kinds).toEqual(new Set(["module", "call_site", "environment_example", "verify_script"]));
  });

  it("adds one request preview per call for Shell", async () => {
    const { blueprint, files } = await filesOf("shell-explicit-subtasks");

    expect(files.filter((file) => file.kind === "request_preview")).toHaveLength(blueprint.calls.length);
  });

  // ADR-0016 §8: where the API is, is not the renderer's to say. The page
  // shows the file as rendered, so it holds no host either.
  it("asks for the API's address and fills in none", async () => {
    for (const name of ["calculated-cost", "shell-calculated-cost"]) {
      const { files } = await filesOf(name);
      const environment = files.find((file) => file.kind === "environment_example");

      expect(environment?.contents).toMatch(/^UBB_BASE_URL=$/m);
      expect(environment?.contents).toMatch(/^UBB_API_KEY=$/m);
    }
  });

  it("renders a Blueprint that is not ready, as files that say so", async () => {
    const { files } = await filesOf("scaffold");

    expect(files.some((file) => file.kind === "module")).toBe(true);
  });

  // ⚠ REFUSED, NOT THROWN AT THE PAGE. A document the renderer cannot read —
  // a shape or a renderer contract it does not know — is what the page shows,
  // in place, rather than a crashed route.
  it("is refused, saying why, for a shape the renderer does not read", async () => {
    const blueprint = await loadBlueprintFixture("calculated-cost");

    const shape = artifactOf({ ...blueprint, schema_version: 2 });
    const contract = artifactOf({ ...blueprint, renderer_contract_version: 9 });

    expect(shape).toEqual({ kind: "refused", reason: expect.stringContaining("given 2") });
    expect(contract).toEqual({ kind: "refused", reason: expect.stringContaining("resolved for 9") });
  });

  it("titles every kind of file the renderer writes", async () => {
    const { files } = await filesOf("shell-calculated-cost");

    for (const file of files) expect(FILE_KIND_TITLES[file.kind]).toBeTruthy();
  });
});

describe("a request preview, beside the call it previews", () => {
  it("pairs each preview with its call, in order", async () => {
    const { blueprint, files } = await filesOf("shell-direct-task-events");

    const { paired, unpaired } = previewsByCall(blueprint, files);

    expect(unpaired).toEqual([]);
    expect(paired.map(({ call }) => call)).toEqual(blueprint.calls);
    for (const { call, preview } of paired) {
      expect(preview?.contents).toContain(`operation_id = "${call.operation_id}"`);
    }
  });

  // ⚠ PAIRED BY POSITION, CHECKED BY OPERATION. The renderer writes previews
  // in call order today; if it ever does not, a preview shown under the wrong
  // call would describe a request that call does not send.
  it("pairs nothing it cannot check", async () => {
    const { blueprint, files } = await filesOf("shell-direct-task-events");
    const previews = files.filter((file) => file.kind === "request_preview");
    const others = files.filter((file) => file.kind !== "request_preview");

    const { paired, unpaired } = previewsByCall(blueprint, [...others, ...[...previews].reverse()]);

    expect(paired.every(({ preview }) => preview === null)).toBe(true);
    expect(unpaired).toHaveLength(previews.length);
  });

  it("pairs nothing for a target that writes no previews", async () => {
    const { blueprint, files } = await filesOf("calculated-cost");

    const { paired, unpaired } = previewsByCall(blueprint, files);

    expect(paired.every(({ preview }) => preview === null)).toBe(true);
    expect(unpaired).toEqual([]);
  });
});

describe("a downloaded file's name", () => {
  it("is the file's own name, without the folder it sits in", () => {
    expect(downloadName("call_sites/record_chat_completion.py")).toBe("record_chat_completion.py");
    expect(downloadName(".env.example")).toBe(".env.example");
  });
});
