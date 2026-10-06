/**
 * The branches the renderer is held to, and reading what it returned.
 *
 * Everything a test asserts is over the text `render` returns. Nothing in
 * this directory reaches into the renderer for a template or a helper: the
 * forms a comment may take, and what a literal looks like once Python has
 * read it back, are worked out here independently, so a mistake in the
 * renderer is contradicted rather than reproduced.
 */
import { render, type RenderedFile } from "../../src/index.ts";
import type { ResolvedIntegrationBlueprint } from "../../src/blueprint.ts";
import { fixture } from "./fixtures.ts";
import { facts, type FileFacts } from "./python.ts";

/** A value no credential is shaped like, planted where a secret would be. */
export const PLANTED = "planted-where-a-secret-would-be";

/**
 * A calculated-cost Blueprint with a value put on every secret token: a
 * document the server never answers, to show what the renderer does with one.
 */
export function withAPlantedSecret(name = "calculated-cost"): ResolvedIntegrationBlueprint {
  const blueprint = fixture(name);
  for (const call of blueprint.calls) {
    for (const argument of call.arguments) {
      if (argument.binding_class === "secret_reference") argument.value = PLANTED;
    }
  }
  return blueprint;
}

type Branches = Readonly<Record<string, () => ResolvedIntegrationBlueprint>>;

/** The Python target's branches, and the Blueprint each renders. */
export const PYTHON_BRANCHES: Branches = {
  "calculated-cost": () => fixture("calculated-cost"),
  "reported-cost": () => fixture("reported-cost"),
  "direct-task-events": () => fixture("direct-task-events"),
  "explicit-subtasks": () => fixture("explicit-subtasks"),
  "fixed-price": () => fixture("fixed-price"),
  scaffold: () => fixture("scaffold"),
  blocked: () => fixture("blocked"),
  constant: () => fixture("constant"),
  "secret-references": () => withAPlantedSecret(),
  "odd-names": () => fixture("odd-names"),
  "draft-preview": () => fixture("draft-preview"),
};

/**
 * The shell target's: the same branches resolved for it, and one more — the
 * Python branch's own declarations, which a shell file cannot read.
 */
export const SHELL_BRANCHES: Branches = {
  "shell-calculated-cost": () => fixture("shell-calculated-cost"),
  "shell-reported-cost": () => fixture("shell-reported-cost"),
  "shell-direct-task-events": () => fixture("shell-direct-task-events"),
  "shell-explicit-subtasks": () => fixture("shell-explicit-subtasks"),
  "shell-fixed-price": () => fixture("shell-fixed-price"),
  "shell-scaffold": () => fixture("shell-scaffold"),
  "shell-blocked": () => fixture("shell-blocked"),
  "shell-constant": () => fixture("shell-constant"),
  "shell-secret-references": () => withAPlantedSecret("shell-calculated-cost"),
  "shell-odd-names": () => fixture("shell-odd-names"),
  "shell-draft-preview": () => fixture("shell-draft-preview"),
  "shell-unreadable-shape": () => fixture("shell-unreadable-shape"),
};

/** Every branch with a committed snapshot, and the Blueprint it renders. */
export const BRANCHES: Branches = { ...PYTHON_BRANCHES, ...SHELL_BRANCHES };

export const BRANCH_NAMES = Object.keys(BRANCHES).sort();
export const PYTHON_BRANCH_NAMES = Object.keys(PYTHON_BRANCHES).sort();
export const SHELL_BRANCH_NAMES = Object.keys(SHELL_BRANCHES).sort();

const renderedCache = new Map<string, RenderedFile[]>();
const factsCache = new Map<string, Record<string, FileFacts>>();

export function rendered(branch: string): RenderedFile[] {
  let files = renderedCache.get(branch);
  if (files === undefined) {
    files = render(BRANCHES[branch]!());
    renderedCache.set(branch, files);
  }
  return files;
}

/** What Python's parser finds in a branch's files, asked once per branch. */
export function factsOf(branch: string): Record<string, FileFacts> {
  let found = factsCache.get(branch);
  if (found === undefined) {
    found = facts(rendered(branch));
    factsCache.set(branch, found);
  }
  return found;
}

export function only(files: readonly RenderedFile[], kind: RenderedFile["kind"]): RenderedFile {
  const found = files.filter((file) => file.kind === kind);
  if (found.length !== 1) {
    throw new Error(`expected one ${kind} file, found ${found.length}`);
  }
  return found[0]!;
}

export function moduleOf(branch: string): RenderedFile {
  return only(rendered(branch), "module");
}

/** The lines of a `#`-commented text file that are comments, without the `#`. */
export function hashComments(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("#"));
}

/** A comment as its text: without the `#` and the space after it. */
export function commentText(comment: string): string {
  return comment.replace(/^#\s?/, "");
}

export interface Provenance {
  name: string;
  value: unknown;
  qualifiers: [string, unknown][];
}

function parseQualifiers(text: string): [string, unknown][] | null {
  if (text === "") return [];
  const qualifiers: [string, unknown][] = [];
  for (const part of text.split(" · ").slice(1)) {
    const space = part.indexOf(" ");
    if (space < 1) return null;
    const qualifier = part.slice(0, space);
    if (!/^[a-z_]+$/.test(qualifier)) return null;
    try {
      qualifiers.push([qualifier, JSON.parse(part.slice(space + 1))]);
    } catch {
      return null;
    }
  }
  return qualifiers;
}

/**
 * A comment read as a provenance statement — `<name> = <json>` and then any
 * number of ` · <qualifier> <json>` — or `null` where it is not one.
 *
 * Written against the grammar and not against the renderer. A name may itself
 * hold ` = ` and a JSON string may hold ` · `, so every split is tried and
 * the first that reads as the whole form is the answer.
 */
export function provenanceOf(text: string): Provenance | null {
  let from = 0;
  for (;;) {
    const equals = text.indexOf(" = ", from);
    if (equals < 1) return null;
    from = equals + 1;
    const name = text.slice(0, equals);
    const rest = text.slice(equals + 3);
    const breaks = [rest.length];
    for (let at = rest.indexOf(" · "); at !== -1; at = rest.indexOf(" · ", at + 1)) {
      breaks.push(at);
    }
    for (const end of breaks.sort((left, right) => left - right)) {
      let value: unknown;
      try {
        value = JSON.parse(rest.slice(0, end));
      } catch {
        continue;
      }
      const qualifiers = parseQualifiers(rest.slice(end));
      if (qualifiers !== null) return { name, value, qualifiers };
    }
  }
}
