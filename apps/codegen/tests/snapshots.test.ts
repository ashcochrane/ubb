/**
 * Every renderer branch of every target, pinned as the files it returns
 * (#577, #578, gate G24).
 *
 * One directory per branch under `tests/__snapshots__/`, holding the files
 * exactly as `render` returned them — real `.py` and `.sh` files and a real
 * `.env.example`, so a change to what a tenant is handed is read in a diff as
 * the thing itself. A shell branch's directory is `shell-<branch>`.
 * `pnpm test:update` re-takes them.
 */
import { existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { render } from "../src/index.ts";
import { fixture, PACKAGE_ROOT } from "./support/fixtures.ts";
import {
  BRANCH_NAMES,
  BRANCHES,
  PLANTED,
  PYTHON_BRANCH_NAMES,
  rendered,
  SHELL_BRANCH_NAMES,
  withAPlantedSecret,
} from "./support/rendered.ts";

const SNAPSHOTS = join(PACKAGE_ROOT, "tests", "__snapshots__");

function filesUnder(directory: string, prefix = ""): string[] {
  if (!existsSync(directory)) return [];
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    const relative = prefix === "" ? entry : `${prefix}/${entry}`;
    return statSync(path).isDirectory() ? filesUnder(path, relative) : [relative];
  });
}

describe.each(BRANCH_NAMES)("the %s branch", (branch) => {
  it("renders the files its snapshot holds", async () => {
    for (const file of rendered(branch)) {
      await expect(file.contents).toMatchFileSnapshot(join(SNAPSHOTS, branch, file.path));
    }
  });

  it("holds no snapshot of a file it no longer renders", () => {
    expect(filesUnder(join(SNAPSHOTS, branch)).sort()).toEqual(
      rendered(branch)
        .map((file) => file.path)
        .sort(),
    );
  });
});

describe("the snapshots", () => {
  it("are of the branches the tests render, and of no other", () => {
    expect(readdirSync(SNAPSHOTS).filter((entry) => !entry.includes(".")).sort()).toEqual(
      BRANCH_NAMES,
    );
  });

  const NAMED = [
    "calculated-cost",
    "reported-cost",
    "direct-task-events",
    "explicit-subtasks",
    "fixed-price",
    "scaffold",
    "blocked",
    "secret-references",
    // #583: a supplier's cost read off the response, with its currency pinned
    // and with its currency read beside it.
    "response-cost",
    "response-cost-read-currency",
  ];

  it("cover every branch the ticket names", () => {
    expect(BRANCH_NAMES).toEqual(expect.arrayContaining(NAMED));
  });

  it("cover the same branches for the shell target, and the one only it has", () => {
    // Every branch the Python target is pinned for, pinned for shell too —
    // each rendered from a Blueprint resolved for that target.
    expect(SHELL_BRANCH_NAMES).toEqual(
      [...PYTHON_BRANCH_NAMES.map((branch) => `shell-${branch}`), "shell-unreadable-shape"].sort(),
    );
    expect(SHELL_BRANCH_NAMES).toEqual(
      expect.arrayContaining(NAMED.map((branch) => `shell-${branch}`)),
    );
    for (const branch of SHELL_BRANCH_NAMES) {
      expect(BRANCHES[branch]!().target, branch).toBe("shell_http");
    }
    for (const branch of PYTHON_BRANCH_NAMES) {
      expect(BRANCHES[branch]!().target, branch).toBe("python_sdk");
    }
  });

  it("are kept in directories of their own, a target's files never beside another's", () => {
    for (const branch of BRANCH_NAMES) {
      const shell = rendered(branch).some((file) => file.path.endsWith(".sh"));
      const python = rendered(branch).some((file) => file.path.endsWith(".py"));

      expect(shell, branch).toBe(branch.startsWith("shell-"));
      expect(python, branch).toBe(!branch.startsWith("shell-"));
    }
  });
});

describe("rendering", () => {
  it("is a function of the Blueprint and of nothing else", () => {
    for (const branch of BRANCH_NAMES) {
      expect(render(BRANCHES[branch]!())).toEqual(render(BRANCHES[branch]!()));
    }
  });

  it("leaves the Blueprint it was given as it found it", () => {
    const blueprint = fixture("explicit-subtasks");
    render(blueprint);
    expect(blueprint).toEqual(fixture("explicit-subtasks"));
  });

  it.each(["calculated-cost", "shell-calculated-cost"])(
    "writes the same files whatever a secret token carries as a value: %s",
    (name) => {
      // A secret token's value is never read, so planting one changes nothing.
      expect(render(withAPlantedSecret(name))).toEqual(render(fixture(name)));
      expect(JSON.stringify(withAPlantedSecret(name))).toContain(PLANTED);
    },
  );
});
