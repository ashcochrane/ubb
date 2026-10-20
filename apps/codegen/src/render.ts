/**
 * `render`: a resolved Integration Blueprint in, the files of an artifact out.
 *
 * The server decides what a tenant's integration code must MEAN and says so
 * as a Blueprint; this function decides how that is EXPRESSED (#184 §1). It
 * is pure: the same Blueprint is always the same files, it reads nothing but
 * its argument, and it has nothing to reach a console, a network, a
 * filesystem or a clock with.
 *
 * It renders a Blueprint that is not ready — as files that say what is
 * missing and refuse to run. It REFUSES, with `BlueprintNotRenderable`, only
 * a document it cannot read: a shape or a renderer contract it does not
 * know, a target it has no renderer for, or a token that breaks what the
 * contract promises. A reader that guessed at an unknown shape would write a
 * file that is wrong and looks right.
 */
import {
  BlueprintNotRenderable,
  type CodeTarget,
  type ResolvedIntegrationBlueprint,
} from "./blueprint.ts";
import { renderPython } from "./python/index.ts";
import { renderShell } from "./shell/index.ts";

/**
 * Which part of an artifact a file is. A `request_preview` is documentation
 * of one request a shell artifact sends: it is not run, carries no verdict,
 * and never stands in for the `module`.
 */
export type FileKind =
  | "module"
  | "call_site"
  | "environment_example"
  | "verify_script"
  | "request_preview";

export interface RenderedFile {
  readonly kind: FileKind;
  /** Where the file goes, relative to wherever the artifact is put. */
  readonly path: string;
  /** The whole file, ending in a newline. Newlines are `\n`. */
  readonly contents: string;
}

/** The document shapes this renderer reads. */
export const READABLE_SCHEMA_VERSIONS: readonly number[] = [1];

/**
 * The renderer contracts this renderer was written to. Contract 2 (#583) let
 * a runtime value of a field of its own carry a `source_path` fact. Contract
 * 3 (#603, #584) is the one written to now: a measured quantity is exact TEXT
 * on the wire, sent as text and never as a JSON number, with no digit limit,
 * and a constant quantity's token is a configured literal carrying its
 * declared value. A renderer written to contract 2 would send a quantity as
 * a number and write a constant as missing, so it refuses a contract-3
 * document rather than misreading it. This renderer reads the one contract
 * it is written and tested against, as it reads every version (ADR-0016 §7):
 * the platform resolves contract 3 alone, and an older document is refused
 * like any other version outside the set.
 */
export const READABLE_RENDERER_CONTRACT_VERSIONS: readonly number[] = [3];

const TARGETS: Partial<
  Record<CodeTarget, (blueprint: ResolvedIntegrationBlueprint) => RenderedFile[]>
> = {
  python_sdk: renderPython,
  shell_http: renderShell,
};

export function render(blueprint: ResolvedIntegrationBlueprint): RenderedFile[] {
  if (!READABLE_SCHEMA_VERSIONS.includes(blueprint.schema_version)) {
    throw new BlueprintNotRenderable(
      `this renderer reads Blueprint schema ${READABLE_SCHEMA_VERSIONS.join(", ")}, ` +
        `and was given ${blueprint.schema_version}`,
    );
  }
  if (!READABLE_RENDERER_CONTRACT_VERSIONS.includes(blueprint.renderer_contract_version)) {
    throw new BlueprintNotRenderable(
      `this renderer was written to renderer contract ` +
        `${READABLE_RENDERER_CONTRACT_VERSIONS.join(", ")}, and the Blueprint was ` +
        `resolved for ${blueprint.renderer_contract_version}`,
    );
  }
  const target = TARGETS[blueprint.target];
  if (target === undefined) {
    throw new BlueprintNotRenderable(`there is no renderer for the target ${blueprint.target}`);
  }
  return target(blueprint);
}
