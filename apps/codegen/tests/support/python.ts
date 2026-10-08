/**
 * Asking a Python interpreter about rendered files.
 *
 * The files are written to a temporary directory exactly as `render` returned
 * them and handed to `tests/harness/harness.py`. The interpreter must have the
 * SDK's dependencies installed; the SDK itself is taken from this checkout,
 * so what a generated module is run against is the SDK in this tree.
 *
 * `UBB_CODEGEN_PYTHON` names the interpreter; unset, it is `python`. There is
 * no skip: a machine with no usable interpreter fails these tests, because a
 * renderer whose output nobody compiled has not been tested.
 */
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, dirname, join } from "node:path";

import type { RenderedFile } from "../../src/index.ts";
import { PACKAGE_ROOT, REPO_ROOT } from "./fixtures.ts";

const HARNESS = join(PACKAGE_ROOT, "tests", "harness", "harness.py");
const INTERPRETER = process.env.UBB_CODEGEN_PYTHON ?? "python";

export interface Handler {
  function: string | null;
  catches: string | null;
  reraises: boolean;
}

export interface FunctionFacts {
  positional: string[];
  required_keywords: string[];
  optional_keywords: string[];
  has_docstring: boolean;
  calls: { callee: string; keywords: Record<string, unknown> }[];
}

export interface FileFacts {
  comments: string[];
  constants: unknown[];
  strings: string[];
  handlers: Handler[];
  functions: Record<string, FunctionFacts>;
  names: string[];
  imports: string[];
  has_module_docstring: boolean;
}

/** Write `files` out as they were returned, run `use`, and clean up. */
export function onDisk<T>(files: readonly RenderedFile[], use: (directory: string) => T): T {
  const directory = mkdtempSync(join(tmpdir(), "ubb-codegen-"));
  try {
    for (const file of files) {
      const path = join(directory, file.path);
      mkdirSync(dirname(path), { recursive: true });
      writeFileSync(path, file.contents, "utf-8");
    }
    return use(directory);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

function harness(...argv: string[]): unknown {
  const ran = spawnSync(INTERPRETER, [HARNESS, ...argv], {
    encoding: "utf-8",
    env: {
      ...process.env,
      PYTHONPATH: [join(REPO_ROOT, "ubb-sdk"), process.env.PYTHONPATH ?? ""]
        .filter(Boolean)
        .join(delimiter),
      PYTHONDONTWRITEBYTECODE: "1",
      PYTHONIOENCODING: "utf-8",
    },
  });
  if (ran.error) throw ran.error;
  if (ran.status !== 0) {
    throw new Error(`harness ${argv[0]} exited ${ran.status}:\n${ran.stderr}`);
  }
  return JSON.parse(ran.stdout);
}

/** Each Python file, and the reason Python refuses it — `null` for none. */
export function compiled(files: readonly RenderedFile[]): Record<string, string | null> {
  return onDisk(files, (directory) => harness("compile", directory)) as Record<
    string,
    string | null
  >;
}

/** What Python's own parser finds in each Python file. */
export function facts(files: readonly RenderedFile[]): Record<string, FileFacts> {
  return onDisk(files, (directory) => harness("facts", directory)) as Record<
    string,
    FileFacts
  >;
}

/** The generated conversion, run over the platform's own cases. */
export function reportedCost(
  files: readonly RenderedFile[],
  casesPath: string,
): { amounts: number; currencies: number; disagreements: unknown[] } {
  return onDisk(files, (directory) =>
    harness("reported-cost", directory, casesPath),
  ) as { amounts: number; currencies: number; disagreements: unknown[] };
}

/**
 * A supplier's cost read off a response, run through `record` — the generated
 * record function — over the platform's own rows for one representation and
 * currency (#583). The rows are read by the harness from the platform's file,
 * so no answer passes through a reader that could not hold it.
 */
export function responseCost(
  files: readonly RenderedFile[],
  casesPath: string,
  record: string,
  representation: string,
  currency: string,
): { rows: number; disagreements: unknown[] } {
  return onDisk(files, (directory) =>
    harness("response-cost", directory, casesPath, record, representation, currency),
  ) as { rows: number; disagreements: unknown[] };
}

/**
 * The values of closed registry concepts, and the version of the SDK in this
 * tree, as the SDK's generated vocabulary holds them.
 */
export function registry(...concepts: string[]): {
  sdk_version: string;
  values: Record<string, string[]>;
} {
  return harness("registry", ...concepts) as {
    sdk_version: string;
    values: Record<string, string[]>;
  };
}

/**
 * Import the rendered module against a local server standing where UBB
 * would, and run `script` — Python, with `load()`, `server` and `result` in
 * scope. Returns what the script left in `result`.
 */
export function run<T = unknown>(files: readonly RenderedFile[], script: string): T {
  return onDisk(files, (directory) => {
    const scriptPath = join(directory, "__script__.py");
    writeFileSync(scriptPath, script, "utf-8");
    return harness("run", directory, scriptPath) as T;
  });
}
