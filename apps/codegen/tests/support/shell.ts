/**
 * Asking a shell about rendered files.
 *
 * The files are written to a temporary directory exactly as `render` returned
 * them and handed to `tests/harness/shell_harness.py`, which parses them with
 * `sh` and `bash` and runs them against a local server standing where UBB
 * would. The machine needs a POSIX `sh`, `bash`, `curl` and `jq`, and a
 * Python to run the harness with.
 *
 * WHERE THE SHELL IS. Unset, `UBB_CODEGEN_SHELL_IMAGE` means this machine's
 * own tools: what CI's runner has. Set to the name of a container image, the
 * same harness is run inside it with the directory mounted — for a machine
 * with no such tools of its own, Windows above all, where a Git Bash and a
 * native jq.exe are not what a generated file is ever run in.
 * `tests/harness/Dockerfile` builds the image.
 *
 * There is no skip either way: a machine that can run neither fails these
 * tests, because a shell file nobody ran has not been tested.
 */
import { spawnSync } from "node:child_process";
import { copyFileSync, writeFileSync } from "node:fs";
import { delimiter, join } from "node:path";

import { MESSAGES, SHELL_EXIT, SHELL_MESSAGES, type RenderedFile } from "../../src/index.ts";
import { PACKAGE_ROOT } from "./fixtures.ts";
import { onDisk } from "./python.ts";

const HARNESS_DIRECTORY = join(PACKAGE_ROOT, "tests", "harness");
const INTERPRETER = process.env.UBB_CODEGEN_PYTHON ?? "python";
const IMAGE = process.env.UBB_CODEGEN_SHELL_IMAGE;

/** One request the stand-in server was sent. */
export interface Sent {
  method: string;
  path: string;
  body: Record<string, unknown>;
  /** The body as it arrived, before anything parsed it. */
  raw: string;
  content_type: string | null;
  authorization: string | null;
}

/** What the next request to `path` is answered with. */
export interface Answer {
  path: string;
  /** Fields laid over the route's ordinary answer; `http_status` and
   * `raw_body` change the response itself. */
  answer: Record<string, unknown>;
}

export interface Ran {
  status: number;
  stdout: string;
  stderr: string;
  requests: Sent[];
}

export interface RunOptions {
  /** `sh` unless a test is about `bash`. */
  shell?: "sh" | "bash";
  answers?: Answer[];
  /** Laid over the environment; `null` unsets a variable. */
  environment?: Record<string, string | null>;
}

function harness(directory: string, ...argv: string[]): unknown {
  const ran =
    IMAGE === undefined
      ? spawnSync(INTERPRETER, [join(HARNESS_DIRECTORY, "shell_harness.py"), ...argv], {
          cwd: directory,
          encoding: "utf-8",
          env: {
            ...process.env,
            PYTHONPATH: [HARNESS_DIRECTORY, process.env.PYTHONPATH ?? ""]
              .filter(Boolean)
              .join(delimiter),
            PYTHONDONTWRITEBYTECODE: "1",
            PYTHONIOENCODING: "utf-8",
          },
        })
      : spawnSync(
          "docker",
          [
            "run", "--rm",
            "--volume", `${directory}:/work`,
            "--volume", `${HARNESS_DIRECTORY}:/harness:ro`,
            "--workdir", "/work",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--env", "PYTHONIOENCODING=utf-8",
            IMAGE,
            "python3", "/harness/shell_harness.py", ...argv,
          ],
          { encoding: "utf-8" },
        );
  if (ran.error) throw ran.error;
  if (ran.status !== 0) {
    throw new Error(`shell harness ${argv[0]} exited ${ran.status}:\n${ran.stderr}`);
  }
  return JSON.parse(ran.stdout);
}

/** Each shell file, and the reason a shell refuses to parse it — `null` for
 * none. Asked of `sh` and of `bash`. */
export function parsed(files: readonly RenderedFile[]): Record<string, string | null> {
  return onDisk(files, (directory) => harness(directory, "syntax")) as Record<
    string,
    string | null
  >;
}

/**
 * Run `script` — shell, which sources the rendered files itself, as a tenant
 * does — with the two documented variables set and a local server standing
 * where UBB would.
 */
export function runShell(
  files: readonly RenderedFile[],
  script: string,
  options: RunOptions = {},
): Ran {
  return onDisk(files, (directory) => {
    writeFileSync(join(directory, "__plan__.json"), JSON.stringify({ script, ...options }), "utf-8");
    return harness(directory, "run", "__plan__.json") as Ran;
  });
}

/** What a refusal about the currency, and not about the amount, says. */
const ABOUT_THE_CURRENCY = [
  MESSAGES.currencyUnknown,
  MESSAGES.currencyNone,
  MESSAGES.currencyDisagrees,
  MESSAGES.currencyNotText,
];

/**
 * A supplier's cost read off a response, run through `record` — the generated
 * record function — over the platform's own rows for one representation and
 * currency, under every shell the harness has (#583).
 */
export function responseCostInShell(
  files: readonly RenderedFile[],
  casesPath: string,
  record: string,
  representation: string,
  currency: string,
): { rows: number; shells: string[]; disagreements: unknown[] } {
  return onDisk(files, (directory) => {
    copyFileSync(casesPath, join(directory, "__cases__.json"));
    writeFileSync(
      join(directory, "__messages__.json"),
      JSON.stringify({
        refused_status: SHELL_EXIT.valueRefused.status,
        currency: ABOUT_THE_CURRENCY,
        // A response it does not read at all, rather than the value in it.
        response: [SHELL_MESSAGES.readUnreadable],
      }),
      "utf-8",
    );
    return harness(
      directory,
      "response-cost",
      "__cases__.json",
      record,
      representation,
      currency,
      "__messages__.json",
    ) as { rows: number; shells: string[]; disagreements: unknown[] };
  });
}

/** The generated conversion, run over the platform's own cases under every
 * shell the harness has. */
export function reportedCostInShell(
  files: readonly RenderedFile[],
  casesPath: string,
): { amounts: number; currencies: number; shells: string[]; disagreements: unknown[] } {
  return onDisk(files, (directory) => {
    copyFileSync(casesPath, join(directory, "__cases__.json"));
    writeFileSync(
      join(directory, "__messages__.json"),
      JSON.stringify({
        refused_status: SHELL_EXIT.valueRefused.status,
        // What a refusal about the currency, and not about the amount, says.
        currency: [MESSAGES.currencyUnknown, MESSAGES.currencyNone, MESSAGES.currencyDisagrees],
      }),
      "utf-8",
    );
    return harness(directory, "reported-cost", "__cases__.json", "__messages__.json") as {
      amounts: number;
      currencies: number;
      shells: string[];
      disagreements: unknown[];
    };
  });
}
