/**
 * What a rendered shell file DOES, by running it (#578).
 *
 * The files are written to disk as `render` returned them, sourced by a real
 * `sh` (and a real `bash`), and pointed at a local server standing where UBB
 * would — through `UBB_BASE_URL`, the one seam the artifact itself documents.
 * Nothing is patched: what reaches the wire is what a tenant's script would
 * send, through the curl and the jq on the machine.
 *
 * This is not the execution gate (#582 runs complete artifacts against the
 * real application, and owns the minimal-image fixtures for a missing or an
 * incompatible tool). It is the renderer's own proof that what it wrote
 * sends what was declared, converts money exactly, and stops when told to.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  MESSAGES,
  render,
  SHELL,
  SHELL_EXIT,
  SHELL_FILE,
  SHELL_MESSAGES,
  type RenderedFile,
} from "../src/index.ts";
import type { ResolvedIntegrationBlueprint } from "../src/blueprint.ts";
import { jqNeedsOf } from "../src/shell/probe.ts";
import { everyArgument, fixture, FIXTURES, PACKAGE_ROOT, REPO_ROOT } from "./support/fixtures.ts";
import { BRANCHES, only, rendered, SHELL_BRANCH_NAMES } from "./support/rendered.ts";
import { parsed, reportedCostInShell, runShell, type Ran, type RunOptions, type Sent } from "./support/shell.ts";
import { functionsOf, heredocs, substitutions } from "./support/shellText.ts";

const CONTRACT = JSON.parse(readFileSync(join(REPO_ROOT, "openapi", "v1.json"), "utf-8")) as {
  paths: Record<
    string,
    Record<
      string,
      {
        operationId?: string;
        requestBody?: { content: Record<string, { schema: { $ref: string } }> };
      }
    >
  >;
  components: { schemas: Record<string, { properties: Record<string, unknown> }> };
};

interface Published {
  operationId: string;
  method: string;
  path: string;
  /** The keys the operation's request publishes. */
  keys: string[];
}

/** Every operation of the committed contract that takes a JSON body. */
const PUBLISHED: Published[] = Object.entries(CONTRACT.paths).flatMap(([path, methods]) =>
  Object.entries(methods).flatMap(([method, operation]) => {
    const schema = operation.requestBody?.content["application/json"]?.schema.$ref;
    if (operation.operationId === undefined || schema === undefined) return [];
    const name = schema.slice(schema.lastIndexOf("/") + 1);
    return [
      {
        operationId: operation.operationId,
        method: method.toUpperCase(),
        path,
        keys: Object.keys(CONTRACT.components.schemas[name]!.properties),
      },
    ];
  }),
);

function published(operationId: string): Published {
  const found = PUBLISHED.find((operation) => operation.operationId === operationId);
  if (found === undefined) throw new Error(`${operationId} is not an operation of the contract`);
  return found;
}

/** The operation a request was sent to, by the contract's own routes. */
function operationOf(request: Sent): Published {
  const found = PUBLISHED.filter(
    (operation) =>
      operation.method === request.method &&
      new RegExp(`^${operation.path.replace(/\{[^{}]+\}/g, "[^/]+")}$`).test(request.path),
  );
  if (found.length !== 1) throw new Error(`${request.method} ${request.path} is no one operation`);
  return found[0]!;
}

const SOURCE = ". ./ubb_integration.sh";

/** What a script printed as `name=value` lines. */
function said(ran: Ran): Record<string, string> {
  return Object.fromEntries(
    ran.stdout
      .split("\n")
      .filter((line) => /^[a-z_0-9]+=/.test(line))
      .map((line) => [line.slice(0, line.indexOf("=")), line.slice(line.indexOf("=") + 1)]),
  );
}

function block(files: readonly RenderedFile[], path: string): string[] {
  const found = files.find((file) => file.path === path);
  if (found === undefined) throw new Error(`no ${path}`);
  return found.contents.split("\n").filter((line) => line !== "" && !line.startsWith("#"));
}

/**
 * A script that runs a whole artifact the way its own call-site blocks say
 * to: the blocks as rendered, pasted into a function for the work, with a
 * shell variable of each parameter's name holding a value for it. Nothing of
 * the generated text is changed.
 */
function lifecycle(blueprint: ResolvedIntegrationBlueprint, files: readonly RenderedFile[]) {
  const captured: Record<string, unknown> = {};
  const numbers = new Set<string>();
  const all = everyArgument(blueprint);
  all.forEach((argument, index) => {
    if (argument.name.endsWith(".source_path") && Array.isArray(argument.value)) {
      // A response that holds a number wherever a path is declared to read.
      let at = captured;
      const path = argument.value as string[];
      path.forEach((segment, depth) => {
        if (depth === path.length - 1) at[segment] = 7;
        else at = (at[segment] ??= {}) as Record<string, unknown>;
      });
    }
    if (argument.name.endsWith(".value_type")) {
      const value = all
        .slice(index)
        .find((later) => later.name === argument.name.slice(0, -".value_type".length));
      if (value?.parameter_name) numbers.add(value.parameter_name);
    }
  });
  const values: Record<string, string> = {};
  for (const argument of all) {
    const name = argument.parameter_name;
    if (argument.binding_class !== "runtime_bound" || !name) continue;
    values[name] =
      name === "response" ? "response.json"
      : name === "reported_cost" ? "0.5"
      : name === "outcome" ? "delivered"
      : numbers.has(name) ? "3"
      : `a-${name}`;
  }
  const blocks = files.filter((file) => file.kind === "call_site").map((file) => file.path);
  const inside = blocks.filter((path) => /\/ubb_(start_subtask|record)_/.test(path));
  const work = block(files, "call_sites/run_task.sh");
  const script = [
    SOURCE,
    ...Object.entries(values).map(([name, value]) => `${name}='${value}'`),
    `printf '%s' "$CAPTURED" >response.json`,
    "work() {",
    "  task_id=$1",
    ...inside.flatMap((path) => block(files, path).map((line) => `  ${line}`)),
    ...block(files, "call_sites/close.sh").map((line) => `  ${line}`),
    "}",
    ...work.slice(work.indexOf("}") + 1),
    `printf 'status=%s\\n' "$?"`,
  ].join("\n");
  return { script, values, environment: { CAPTURED: JSON.stringify(captured) } };
}

function runLifecycle(branch: string, options: RunOptions = {}): { ran: Ran; values: Record<string, string> } {
  const files = rendered(branch);
  const { script, values, environment } = lifecycle(BRANCHES[branch]!(), files);
  return {
    ran: runShell(files, script, { ...options, environment: { ...environment, ...options.environment } }),
    values,
  };
}

const COMPLETE = SHELL_BRANCH_NAMES.filter(
  (branch) => BRANCHES[branch]!().readiness === "complete",
);

describe("a complete shell file, run", () => {
  it("starts, records and closes through the operations the Blueprint names", () => {
    const blueprint = fixture("shell-calculated-cost");
    const ran = runShell(
      rendered("shell-calculated-cost"),
      `${SOURCE}
printf '%s' '{"usageMetadata":{"promptTokenCount":1200,"candidatesTokenCount":340}}' >response.json
work() {
  ubb_record_chat_completion customer_id=customer-1 idempotency_key=call-1 \\
    task_id="$1" response=response.json searches=2 || return $?
  ubb_close_task task_id="$1" outcome=delivered
}
ubb_run_task work customer_id=customer-1 idempotency_key=work-1 environment=production
printf 'status=%s\\ntask=%s\\n' "$?" "$UBB_TASK_ID"
`,
    );

    expect(said(ran)).toEqual({ status: "0", task: "task_1" });
    const [start, record, close] = ran.requests;
    expect(ran.requests).toHaveLength(3);
    expect(start!.body).toEqual({
      customer_id: "customer-1",
      idempotency_key: "work-1",
      task_type: "report_generation",
      grouping_fields: { environment: "production" },
    });
    expect(record!.body).toEqual({
      customer_id: "customer-1",
      idempotency_key: "call-1",
      task_id: "task_1",
      event_type: "chat.completion",
      provider: "google",
      measurements: { input_tokens: 1200, output_tokens: 340, searches: 2 },
    });
    expect(close!.body).toEqual({ outcome: "delivered" });

    // Each request is the operation the Blueprint named for that call, at
    // the route the committed contract publishes it at.
    const operations = blueprint.calls.map((call) => published(call.operation_id));
    expect(ran.requests.map((request) => request.method)).toEqual(
      operations.map((operation) => operation.method),
    );
    expect(start!.path).toBe(operations[0]!.path);
    expect(record!.path).toBe(operations[1]!.path);
    expect(close!.path).toBe(operations[2]!.path.replace("{task_id}", "task_1"));
    for (const request of ran.requests) expect(request.content_type).toBe("application/json");
  });

  it.each(COMPLETE)(
    "sends only keys the operation's request publishes: %s, run as its own blocks say",
    (branch) => {
      const blueprint = BRANCHES[branch]!();
      const { ran } = runLifecycle(branch);

      expect(said(ran), ran.stderr).toEqual({ status: "0" });
      // One request for every call of the Blueprint: nothing was left out of
      // what this reads.
      expect(ran.requests.map((request) => operationOf(request).operationId).sort()).toEqual(
        blueprint.calls.map((call) => call.operation_id).sort(),
      );
      for (const request of ran.requests) {
        const operation = operationOf(request);
        const unpublished = Object.keys(request.body).filter(
          (key) => !operation.keys.includes(key),
        );
        expect(Object.keys(request.body).length, operation.operationId).toBeGreaterThan(0);
        expect(unpublished, operation.operationId).toEqual([]);
      }
    },
  );

  it("reads these branches' published keys off a contract that has some", () => {
    // The vacuity guard of the case above: every operation a Blueprint names
    // has a request in the committed contract, with keys, and one a file
    // could have sent is not among them.
    expect(COMPLETE.length).toBeGreaterThanOrEqual(8);
    for (const operationId of [
      "api_v1_task_endpoints_start_task",
      "api_v1_metering_endpoints_record_usage",
      "api_v1_task_endpoints_close_task",
    ]) {
      expect(published(operationId).keys.length).toBeGreaterThan(2);
    }
    // The SDK's own name for when work happened is not the wire's, and the
    // work a close names is in its route and not its body.
    expect(published("api_v1_metering_endpoints_record_usage").keys).toContain("effective_at");
    expect(published("api_v1_metering_endpoints_record_usage").keys).not.toContain("recorded_at");
    expect(published("api_v1_task_endpoints_close_task").keys).not.toContain("task_id");
  });

  it("sends why work failed only where it is said, under the keys a close publishes", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_close_task task_id=t-1 outcome=failed outcome_reason=timeout reason_detail="it's \\"late\\""
ubb_close_task task_id=t-2 outcome=cancelled
printf 'status=%s\\n' "$?"
`,
    );

    expect(said(ran)).toEqual({ status: "0" });
    expect(ran.requests.map((request) => [request.path, request.body])).toEqual([
      ["/api/v1/tasks/t-1/close", { outcome: "failed", outcome_reason: "timeout", reason_detail: 'it\'s "late"' }],
      ["/api/v1/tasks/t-2/close", { outcome: "cancelled" }],
    ]);
  });

  it("refuses a value that would change the route it is written into", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
for work in 't-1/../../customers' .. . 't 1' 't?x=1' 't#1' 't%2e'; do
  ubb_close_task task_id="$work" outcome=delivered
  printf 'status_%s=%s\\n' "$((count = \${count:-0} + 1))" "$?"
done
`,
    );

    // A slash, a dot segment curl would resolve, and anything a URL gives a
    // meaning to: each refused, and nothing sent to a route nobody named.
    expect(Object.values(said(ran))).toEqual(Array(7).fill(String(SHELL_EXIT.valueRefused.status)));
    expect(ran.stderr).toContain(`ubb_close_task: task_id ${SHELL_MESSAGES.urlValue}`);
    expect(ran.requests).toEqual([]);
  });

  it("reads the credential from the environment and nowhere else", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_start_task customer_id=c idempotency_key=w
printf 'status=%s\\n' "$?"
`,
    );

    expect(said(ran)).toEqual({ status: "0" });
    expect(ran.requests.map((request) => request.authorization)).toEqual([
      "Bearer not-a-real-key",
    ]);
    for (const file of rendered("shell-direct-task-events")) {
      expect(file.contents).not.toContain("not-a-real-key");
    }
  });

  it.each([
    ["UBB_BASE_URL", null],
    ["UBB_BASE_URL", ""],
    ["UBB_API_KEY", null],
    ["UBB_API_KEY", ""],
  ] as const)("holds no host and no key of its own: with %s unset or empty it refuses, naming it (%j)", (variable, value) => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_start_task customer_id=c idempotency_key=w
printf 'status=%s\\n' "$?"
`,
      { environment: { [variable]: value } },
    );

    expect(said(ran)).toEqual({ status: String(SHELL_EXIT.notConfigured.status) });
    expect(ran.stderr).toContain(`${variable} ${MESSAGES.environmentNotSet}`);
    expect(ran.requests).toEqual([]);
  });

  it("refuses, naming it, a runtime value left out, passed empty, or not the call's", () => {
    const ran = runShell(
      rendered("shell-calculated-cost"),
      `${SOURCE}
ubb_start_task customer_id=c idempotency_key=w
printf 'left_out=%s\\n' "$?"
ubb_start_task customer_id=c idempotency_key=w environment=
printf 'empty=%s\\n' "$?"
ubb_start_task customer_id=c idempotency_key=w environment=production region=eu
printf 'not_its=%s\\n' "$?"
ubb_record_chat_completion customer_id=c idempotency_key=e task_id=t response=r.json
printf 'record=%s\\n' "$?"
ubb_start_task customer_id=c idempotency_key=w environment=production api_key=would-be-a-secret
printf 'echoed=%s\\n' "$?"
`,
    );
    const usage = String(SHELL_EXIT.usage.status);

    expect(said(ran)).toEqual({
      left_out: usage, empty: usage, not_its: usage, record: usage, echoed: usage,
    });
    expect(ran.stderr).toContain(`ubb_start_task: environment ${SHELL_MESSAGES.missing}`);
    expect(ran.stderr).toContain(`ubb_start_task: region ${SHELL_MESSAGES.unknown}`);
    expect(ran.stderr).toContain(`ubb_record_chat_completion: searches ${SHELL_MESSAGES.missing}`);
    // What is printed of an argument that is not the call's is its name.
    expect(ran.stderr).not.toContain("would-be-a-secret");
    expect(ran.requests).toEqual([]);
  });

  it("refuses a quantity that is not a whole number it can carry exactly", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
for quantity in three 1.5 007 1e3 9999999999999999 '3; touch made-by-a-quantity' '"3"'; do
  ubb_record_search_run customer_id=c idempotency_key=e task_id=t searches="$quantity"
  printf 'status_%s=%s\\n' "$((count = \${count:-0} + 1))" "$?"
done
ubb_record_search_run customer_id=c idempotency_key=e task_id=t searches=999999999999999
printf 'largest=%s\\n' "$?"
ubb_record_search_run customer_id=c idempotency_key=e task_id=t searches=0
printf 'zero=%s\\n' "$?"
ls
`,
    );
    const answers = said(ran);

    // Refused as a value, by the file, each naming the parameter: not as a
    // parameter left out, and not by jq or by the API.
    expect(Object.values(answers).slice(0, 7)).toEqual(
      Array(7).fill(String(SHELL_EXIT.valueRefused.status)),
    );
    expect(
      ran.stderr.split("\n").filter((line) =>
        line.startsWith(`ubb_record_search_run: searches ${SHELL_MESSAGES.wholeNumber}`),
      ),
    ).toHaveLength(7);
    expect(ran.stdout).not.toMatch(/made-by/);
    expect(answers.largest).toBe("0");
    expect(answers.zero).toBe("0");
    expect(ran.requests.map((request) => request.raw)).toEqual([
      expect.stringContaining('"measurements":{"searches":999999999999999}'),
      expect.stringContaining('"measurements":{"searches":0}'),
    ]);
  });

  it.each(["sh", "bash"] as const)("runs the same under %s, with set -eu or without", (shell) => {
    const plain = runLifecycle("shell-explicit-subtasks", { shell });
    const files = rendered("shell-explicit-subtasks");
    const { script, environment } = lifecycle(BRANCHES["shell-explicit-subtasks"]!(), files);
    const strict = runShell(files, `set -eu\n${script}`, { shell, environment });

    expect(said(plain.ran)).toEqual({ status: "0" });
    expect(said(strict)).toEqual({ status: "0" });
    expect(plain.ran.requests).toHaveLength(4);
    expect(strict.requests.map((request) => [request.path, request.body])).toEqual(
      plain.ran.requests.map((request) => [request.path, request.body]),
    );
    // The Subtask is started under the work it is inside, and the event is
    // the one the block was told it belongs to.
    expect(strict.requests[1]!.body).toEqual({
      customer_id: "a-customer_id",
      idempotency_key: "a-idempotency_key",
      parent_task_id: "task_1",
      task_type: "summarise",
      grouping_fields: { phase: "a-phase" },
    });
    expect(strict.requests[2]!.body.measurements).toEqual({ candidate_tokens: 7, prompt_tokens: 7 });
  });

  it("refuses to record from a response that does not hold what a declared path reads", () => {
    const ran = runShell(
      rendered("shell-calculated-cost"),
      `${SOURCE}
printf '%s' '{"usageMetadata":{"promptTokenCount":12}}' >missing.json
printf '%s' '{"usageMetadata":{"promptTokenCount":12,"candidatesTokenCount":9007199254740993}}' >inexact.json
printf '%s' '{"usageMetadata":{"promptTokenCount":12,"candidatesTokenCount":"340"}}' >text.json
printf '%s' '{"usageMetadata":{"promptTokenCount":12,"candidatesTokenCount":3.5}}' >fraction.json
printf '%s' 'not json' >malformed.json
for response in missing.json inexact.json text.json fraction.json malformed.json absent.json; do
  ubb_record_chat_completion customer_id=c idempotency_key=e task_id=t response="$response" searches=1
  printf '%s=%s\\n' "\${response%.json}" "$?"
done
`,
    );
    const answers = said(ran);
    const refused = String(SHELL_EXIT.valueRefused.status);

    // One named status whichever way the response fails to hold the value.
    expect(answers).toEqual({
      missing: refused, inexact: refused, text: refused, fraction: refused,
      malformed: refused, absent: refused,
    });
    expect(ran.stderr).toContain(`${SHELL_MESSAGES.noValue} ["usageMetadata","candidatesTokenCount"]`);
    expect(ran.stderr).toContain(`${SHELL_MESSAGES.inexact} ["usageMetadata","candidatesTokenCount"]`);
    expect(
      ran.stderr.split(`${SHELL_MESSAGES.notWhole} ["usageMetadata","candidatesTokenCount"]`),
    ).toHaveLength(3);
    expect(ran.requests).toEqual([]);
  });
});

describe("preflight", () => {
  // The renderer's own checks, with stand-ins on PATH. Images that really
  // lack a tool, or really carry an old one, are #582's
  // (`tests/code_builder_execution/`).
  const START = `${SOURCE}
ubb_start_task customer_id=c idempotency_key=w
printf 'status=%s\\n' "$?"
`;
  const stub = (name: string, body: string) =>
    `printf '%s\\n' '#!/bin/sh' ${JSON.stringify(body).replaceAll("$", "\\$")} >bin/${name}; chmod +x bin/${name}`;
  const real = (name: string) => `ln -s "$(command -v ${name})" bin/${name}`;
  const CASES: [string, string, string][] = [
    ["jq is absent", real("curl"), SHELL_MESSAGES.jqMissing],
    ["curl is absent", real("jq"), SHELL_MESSAGES.curlMissing],
    [
      "jq cannot run a program of the form the file uses",
      `${real("curl")}; ${stub("jq", "exit 3")}`,
      SHELL_MESSAGES.jqUnusable,
    ],
    [
      // What jq 1.3 and 1.4 lack: everything else is the real jq's.
      "jq runs a program from standard input but has no --argjson",
      `${real("curl")}; ln -s "$(command -v jq)" bin/real-jq; ${stub(
        "jq",
        'case " $* " in *" --argjson "*) exit 2 ;; esac; exec "${0%/*}/real-jq" "$@"',
      )}`,
      SHELL_MESSAGES.jqUnusable,
    ],
    [
      "curl has no --fail-with-body",
      `${real("jq")}; ${stub("curl", 'case "$1" in --fail-with-body) exit 2 ;; esac')}`,
      SHELL_MESSAGES.curlUnusable,
    ],
  ];

  it.each(CASES)("refuses before any request where %s", (_what, tools, message) => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `mkdir bin; ${tools}\nPATH=$PWD/bin\n${START}`,
    );

    expect(said(ran)).toEqual({ status: String(SHELL_EXIT.toolUnavailable.status) });
    expect(ran.stderr.trim()).toBe(message);
    expect(ran.requests).toEqual([]);
  });

  it("probes with nothing of the tenant's, and creates nothing", () => {
    for (const branch of SHELL_BRANCH_NAMES) {
      const preflight = functionsOf(only(rendered(branch), "module").contents).find(
        (defined) => defined.name === "_ubb_preflight",
      )!;
      // No declared name reaches it: the one string its program holds is
      // its own, and the same probe is rendered for files whose programs
      // ask the same of jq.
      const strings = preflight.lines.join("\n").match(/"(?:[^"\\]|\\.)*"/g) ?? [];
      expect(strings.filter((text) => !/^"(\$[A-Za-z_]+|probe)"$/.test(text))).toEqual([]);
      expect(preflight.lines.join("\n")).not.toMatch(/mktemp|>\s*[^&/]|UBB_BASE_URL|UBB_API_KEY/);
    }
  });

  // What a jq program asks of jq, read off rendered text by this test's own
  // reading — not the renderer's — so the two must agree for the test to
  // pass. The probe is the one program whose output is discarded.
  const asked = (text: string) => {
    const lines = text.split("\n");
    const programs: { probe: boolean; options: Set<string>; code: string }[] = [];
    for (let at = 0; at < lines.length; at += 1) {
      if (!/^\s*jq /.test(lines[at]!)) continue;
      const command: string[] = [];
      while (!lines[at]!.includes("<<'UBB_JQ'")) command.push(lines[at++]!);
      command.push(lines[at]!);
      const body: string[] = [];
      for (at += 1; lines[at] !== "UBB_JQ"; at += 1) body.push(lines[at]!);
      programs.push({
        probe: command.join(" ").includes(">/dev/null 2>&1"),
        options: new Set(
          command.join(" ").match(/--[a-z-]+/g)!.filter((o) => o !== "--null-input" && o !== "--from-file"),
        ),
        code: body
          .filter((line) => !line.trim().startsWith("#"))
          .join("\n")
          .replace(/"(?:[^"\\]|\\.)*"/g, '""'),
      });
    }
    const KEYWORDS = new Set(
      "if then elif else end as def reduce foreach try catch label and or true false null".split(" "),
    );
    const of = (chosen: typeof programs) => {
      const code = chosen.map((program) => program.code).join("\n");
      const defined = new Set([...code.matchAll(/\bdef\s+(\w+)/g)].map((match) => match[1]!));
      return {
        options: [...new Set(chosen.flatMap((program) => [...program.options]))].sort(),
        forms: {
          definition: /\bdef\s+\w+\(\s*\$/.test(code),
          variable: /\bas\s+\$/.test(code),
          elif: /\belif\b/.test(code),
          reduce: /\breduce\b/.test(code),
        },
        functions: [
          ...new Set(
            [...code.matchAll(/(?<![$.\w])[A-Za-z_]\w*/g)]
              .map((match) => match[0])
              .filter((word) => !KEYWORDS.has(word) && !defined.has(word)),
          ),
        ].sort(),
      };
    };
    return {
      probes: programs.filter((program) => program.probe).length,
      probe: of(programs.filter((program) => program.probe)),
      programs: of(programs.filter((program) => !program.probe)),
    };
  };

  it("probes for exactly what the file's own programs ask of jq, and no more", () => {
    const seen = new Set<string>();
    for (const branch of SHELL_BRANCH_NAMES) {
      for (const file of rendered(branch).filter((each) => each.path.endsWith(".sh"))) {
        if (file.kind === "call_site") continue;
        const { probes, probe, programs } = asked(file.contents);

        expect(probes, `${branch}/${file.path}`).toBe(1);
        expect(probe, `${branch}/${file.path}`).toEqual(programs);
        programs.options.forEach((option) => seen.add(option));
        programs.functions.forEach((name) => seen.add(name));
      }
    }
    // Not vacuous: between them the files ask for options and functions
    // that only some do, which is what a probe of its own per file is for.
    expect([...seen]).toEqual(
      expect.arrayContaining(["--argjson", "--slurpfile", "fromjson", "keys_unsorted", "getpath"]),
    );
    expect(asked(only(rendered("shell-scaffold"), "module").contents).probe.options).not.toContain(
      "--argjson",
    );
    expect(asked(only(rendered("shell-scaffold"), "verify_script").contents).probe.functions).not.toContain(
      "fromjson",
    );
  });

  it("refuses to render a program that asks jq for what no probe knows", () => {
    const command = (options: string, program: string) =>
      `  jq --null-input ${options} \\\n    --from-file /dev/stdin <<'UBB_JQ'\n  ${program}\nUBB_JQ`;

    expect(() => jqNeedsOf(command("--arg a 1", "$a | ltrimstr(\"x\")"))).toThrow(
      "no probe names the jq function ltrimstr",
    );
    expect(() => jqNeedsOf(command("--rawfile a /dev/null", "$a"))).toThrow(
      "no probe passes the jq option --rawfile",
    );
    expect(() => jqNeedsOf(command("--arg a 1", "try $a catch 1"))).toThrow(
      "no probe uses the jq keyword try",
    );
    // A declared name inside a string is a string, not a function.
    expect(jqNeedsOf(command("--arg a 1", '{"ltrimstr": $a} | tojson'))).toEqual({
      options: ["--arg"],
      forms: [],
      functions: ["tojson"],
    });
  });

  it("does nothing when the file is sourced, and never ends the shell that sourced it", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `PATH=/nowhere
${SOURCE}
printf 'sourced=%s\\n' "$?"
ubb_start_task customer_id=c idempotency_key=w
printf 'status=%s\\n' "$?"
printf 'still=here\\n'
`,
      { environment: { UBB_BASE_URL: null, UBB_API_KEY: null } },
    );

    expect(said(ran)).toEqual({
      sourced: "0",
      status: String(SHELL_EXIT.toolUnavailable.status),
      still: "here",
    });
    expect(ran.requests).toEqual([]);
  });
});

describe("the stop", () => {
  const stop = (scope: string, reason: string) => ({
    path: "/api/v1/metering/usage",
    answer: { stop: true, stop_scope: scope, stop_reason: reason },
  });

  it.each(["sh", "bash"] as const)(
    "returns the reserved status with its metadata set, the event recorded once (%s)",
    (shell) => {
      const ran = runShell(
        rendered("shell-direct-task-events"),
        `set -eu
${SOURCE}
ubb_record_search_run customer_id=c idempotency_key=call-7 task_id=t searches=1 && recorded=0 || recorded=$?
printf 'status=%s\\nreserved=%s\\nmetadata=%s\\n' "$recorded" "$${SHELL.stopExitStatusName}" "$${SHELL_FILE.stopRequested}"
`,
        { shell, answers: [stop("task", "task_cogs_ceiling")] },
      );
      const answers = said(ran);

      expect(answers.status).toBe(String(SHELL.stopExitStatus));
      expect(answers.reserved).toBe("20");
      // The four fields the acknowledgement and the request publish today,
      // by their own names; the key is the one the event was sent under.
      expect(JSON.parse(answers.metadata!)).toEqual({
        event_id: "event_1",
        idempotency_key: "call-7",
        stop_scope: "task",
        stop_reason: "task_cogs_ceiling",
      });
      expect(ran.requests).toHaveLength(1);
    },
  );

  it("shares one status between a task-scoped and a customer-scoped stop, told apart by metadata", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_record_search_run customer_id=c idempotency_key=e1 task_id=t searches=1
printf 'first=%s\\nfirst_metadata=%s\\n' "$?" "$UBB_STOP_REQUESTED"
ubb_record_search_run customer_id=c idempotency_key=e2 task_id=t searches=1
printf 'second=%s\\nsecond_metadata=%s\\n' "$?" "$UBB_STOP_REQUESTED"
`,
      { answers: [stop("task", "task_cogs_ceiling"), stop("customer", "customer_spend_pool")] },
    );
    const answers = said(ran);

    expect(answers.first).toBe("20");
    expect(answers.second).toBe("20");
    expect(JSON.parse(answers.first_metadata!).stop_scope).toBe("task");
    expect(JSON.parse(answers.second_metadata!)).toMatchObject({
      idempotency_key: "e2",
      stop_scope: "customer",
      stop_reason: "customer_spend_pool",
    });
  });

  it("is observed by the boundary, logged, and returned — never as success", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
work() {
  ubb_record_search_run customer_id=c idempotency_key=e1 task_id="$1" searches=1 || return $?
  ubb_record_search_run customer_id=c idempotency_key=e2 task_id="$1" searches=1 || return $?
  ubb_record_search_run customer_id=c idempotency_key=e3 task_id="$1" searches=1 || return $?
  ubb_close_task task_id="$1" outcome=delivered
}
ubb_run_task work customer_id=c idempotency_key=w
printf 'status=%s\\n' "$?"
`,
      { answers: [{ path: "/api/v1/metering/usage", answer: {} }, stop("customer", "customer_spend_pool")] },
    );

    expect(said(ran)).toEqual({ status: "20" });
    // The event that carried the stop was sent once and nothing after it,
    // and nothing was declared about work the stop interrupted.
    expect(ran.requests.map((request) => request.path)).toEqual([
      "/api/v1/tasks", "/api/v1/metering/usage", "/api/v1/metering/usage",
    ]);
    const logged = ran.stderr.trim().split("\n");
    expect(logged).toHaveLength(2);
    expect(logged[0]).toBe(SHELL_MESSAGES.stop);
    expect(logged[1]!.startsWith(`${SHELL.stopMetadata} `)).toBe(true);
    expect(JSON.parse(logged[1]!.slice(SHELL.stopMetadata.length + 1))).toEqual({
      event_id: "event_3",
      idempotency_key: "e2",
      stop_scope: "customer",
      stop_reason: "customer_spend_pool",
    });
  });

  it("is still a stop where the work never looked at the status that carried it", () => {
    // The work ignores what its record returned, carries on, declares the
    // work delivered and returns success. The boundary does not.
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
work() {
  ubb_record_search_run customer_id=c idempotency_key=e1 task_id="$1" searches=1
  ubb_close_task task_id="$1" outcome=delivered
}
ubb_run_task work customer_id=c idempotency_key=w
printf 'status=%s\\n' "$?"
`,
      { answers: [stop("task", "task_cogs_ceiling")] },
    );

    expect(said(ran)).toEqual({ status: "20" });
    expect(ran.stderr).toContain(SHELL_MESSAGES.stop);
    expect(ran.stderr).toContain(`${SHELL.stopMetadata} {"event_id":"event_2","idempotency_key":"e1"`);
  });

  it.each(["sh", "bash"] as const)(
    "is acted on by the stop block as rendered, under set -eu, and the script goes on (%s)",
    (shell) => {
      // The blocks themselves, pasted: the record inside the work, and the
      // block that runs the work and reads how it ended.
      const files = rendered("shell-direct-task-events");
      const block = (name: string) =>
        files
          .find((file) => file.path === `call_sites/${name}.sh`)!
          .contents.split("\n")
          .filter((line) => line !== "" && !line.startsWith("#"));
      const ran = runShell(
        files,
        [
          "set -eu",
          SOURCE,
          "customer_id=c idempotency_key=w searches=1",
          "work() {",
          "  task_id=$1",
          ...block("ubb_record_search_run").map((line) => `  ${line}`),
          "}",
          ...block("stop").map((line) =>
            line === "  :" ? `  printf 'acted_on=%s\\n' "$UBB_STOP_REQUESTED"` : line,
          ),
          `printf 'status=%s\\n' "$work_status"`,
        ].join("\n"),
        { shell, answers: [stop("customer", "customer_spend_pool")] },
      );
      const answers = said(ran);

      // Reached, which `set -e` would have prevented had the block called
      // the boundary as a plain command.
      expect(answers.status).toBe("20");
      expect(JSON.parse(answers.acted_on!)).toMatchObject({ stop_scope: "customer" });
    },
  );

  it("clears an earlier call's stop before a record does anything, so a stop is never a stale one", () => {
    // Owner ruling on PR #598. The first record meets a stop; the second is
    // answered with none, is refused, or never gets as far as being sent.
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_record_search_run customer_id=c idempotency_key=e1 task_id=t searches=1
printf 'first=%s %s\\n' "$?" "$UBB_STOP_REQUESTED"
ubb_record_search_run customer_id=c idempotency_key=e2 task_id=t searches=1
printf 'answered_with_none=%s [%s]\\n' "$?" "$UBB_STOP_REQUESTED"
ubb_record_search_run customer_id=c idempotency_key=e3 task_id=t searches=1
printf 'second_stop=%s\\n' "$?"
ubb_record_search_run customer_id=c idempotency_key=e4 task_id=t
printf 'refused=%s [%s]\\n' "$?" "$UBB_STOP_REQUESTED"
`,
      {
        answers: [
          stop("task", "task_cogs_ceiling"),
          { path: "/api/v1/metering/usage", answer: {} },
          stop("customer", "customer_spend_pool"),
        ],
      },
    );
    const answers = said(ran);

    expect(answers.first).toMatch(/^20 \{"event_id":"event_1"/);
    expect(answers.answered_with_none).toBe("0 []");
    expect(answers.second_stop).toBe("20");
    expect(answers.refused).toBe(`${SHELL_EXIT.usage.status} []`);
  });

  it("answers ubb_run_task with the stop its Task met, whatever a later record left behind", () => {
    // The work swallows a stop and records again, which clears the variable.
    // The runner's own result is still the stop, with its metadata.
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
work() {
  ubb_record_search_run customer_id=c idempotency_key=e1 task_id="$1" searches=1
  ubb_record_search_run customer_id=c idempotency_key=e2 task_id="$1" searches=1
  printf 'inside=[%s]\\n' "$UBB_STOP_REQUESTED"
}
ubb_run_task work customer_id=c idempotency_key=w
printf 'status=%s\\nafter=%s\\n' "$?" "$UBB_STOP_REQUESTED"
`,
      { answers: [stop("task", "task_cogs_ceiling")] },
    );
    const answers = said(ran);

    expect(answers.inside).toBe("[]");
    expect(answers.status).toBe("20");
    expect(JSON.parse(answers.after!)).toMatchObject({ idempotency_key: "e1", stop_scope: "task" });
  });

  it("sets its results in the shell and exports none of them to a child process", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_start_task customer_id=c idempotency_key=w
ubb_record_search_run customer_id=c idempotency_key=e1 task_id="$UBB_TASK_ID" searches=1
printf 'here=%s\\n' "\${UBB_TASK_ID:+set} \${UBB_RESPONSE:+set} \${UBB_STOP_REQUESTED:+set}"
sh -c 'printf "child=%s\\n" "\${UBB_TASK_ID-unset} \${UBB_RESPONSE-unset} \${UBB_STOP_REQUESTED-unset}"'
`,
      { answers: [stop("task", "task_cogs_ceiling")] },
    );

    expect(said(ran)).toEqual({ here: "set set set", child: "unset unset unset" });
  });

  it("overwrites the response with each call's own", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_start_task customer_id=c idempotency_key=w
printf 'start=%s\\n' "$UBB_RESPONSE"
ubb_record_search_run customer_id=c idempotency_key=e1 task_id="$UBB_TASK_ID" searches=1
printf 'record=%s\\n' "$UBB_RESPONSE"
`,
    );
    const answers = said(ran);

    expect(JSON.parse(answers.start!)).toHaveProperty("task_id", "task_1");
    expect(JSON.parse(answers.record!)).toHaveProperty("event_id");
    expect(JSON.parse(answers.record!)).not.toHaveProperty("created_at");
  });

  it("clears an earlier stop before ubb_run_task does anything, a run that is refused among them", () => {
    // The runner returns a stop's status too, so what it leaves in the
    // variable is its own: refused with no command, or at its start, it has
    // met no stop and says none.
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
work() { :; }
ubb_record_search_run customer_id=c idempotency_key=e1 task_id=t searches=1
printf 'stopped=%s\\n' "$?"
ubb_run_task
printf 'no_work=%s [%s]\\n' "$?" "$UBB_STOP_REQUESTED"
ubb_record_search_run customer_id=c idempotency_key=e2 task_id=t searches=1
printf 'stopped_again=%s\\n' "$?"
ubb_run_task work customer_id=c
printf 'start_refused=%s [%s]\\n' "$?" "$UBB_STOP_REQUESTED"
`,
      { answers: [stop("task", "task_cogs_ceiling"), stop("task", "task_cogs_ceiling")] },
    );

    expect(said(ran)).toEqual({
      stopped: "20",
      no_work: `${SHELL_EXIT.usage.status} []`,
      stopped_again: "20",
      start_refused: `${SHELL_EXIT.usage.status} []`,
    });
  });

  it("starts a new piece of work with no stop of an earlier one's", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_record_search_run customer_id=c idempotency_key=e1 task_id=t searches=1
printf 'stopped=%s\\n' "$UBB_STOP_REQUESTED"
ubb_start_task customer_id=c idempotency_key=w2
printf 'after=%s\\n' "$UBB_STOP_REQUESTED"
`,
      { answers: [stop("task", "task_cogs_ceiling")] },
    );

    expect(said(ran).stopped).toContain('"stop_scope":"task"');
    expect(said(ran).after).toBe("");
  });

  it.each([
    ["a refusal by the API", { http_status: 422, raw_body: '{"code":"task_not_active"}' }, 22, '{"code":"task_not_active"}'],
    ["a failure of the API", { http_status: 500, raw_body: "upstream said no" }, 22, "upstream said no"],
  ] as const)("keeps %s its own status, with the body it was answered", (_what, answer, status, body) => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_record_search_run customer_id=c idempotency_key=e1 task_id=t searches=1
printf 'status=%s\\nmetadata=%s\\n' "$?" "$UBB_STOP_REQUESTED"
`,
      { answers: [{ path: "/api/v1/metering/usage", answer }] },
    );

    // curl's own status for an HTTP error: not success, and not a stop.
    expect(said(ran)).toEqual({ status: String(status), metadata: "" });
    expect(ran.stderr).toContain(body);
    expect(ran.requests).toHaveLength(1);
  });

  it("keeps a request that never arrived its own status", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_record_search_run customer_id=c idempotency_key=e1 task_id=t searches=1
printf 'status=%s\\n' "$?"
`,
      { environment: { UBB_BASE_URL: "http://127.0.0.1:1" } },
    );

    expect(said(ran)).toEqual({ status: "7" });
  });

  it("never lets a failure be taken for a stop, whatever status it failed with", () => {
    // A curl that fails with the very status reserved for a stop.
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `mkdir bin
ln -s "$(command -v jq)" bin/jq
printf '%s\\n' '#!/bin/sh' 'case "$1" in --fail-with-body) exit 0 ;; esac' 'exit 20' >bin/curl
chmod +x bin/curl
PATH=$PWD/bin
${SOURCE}
ubb_record_search_run customer_id=c idempotency_key=e1 task_id=t searches=1
printf 'status=%s\\nmetadata=%s\\n' "$?" "$UBB_STOP_REQUESTED"
`,
    );

    expect(said(ran)).toEqual({ status: "1", metadata: "" });
  });

  it.each([
    ["is not JSON", { raw_body: "<html>gateway</html>" }],
    ["is empty", { raw_body: "" }],
    ["carries no event_id", { raw_body: '{"stop":true,"stop_scope":"task"}' }],
    ["is not an object", { raw_body: "[]" }],
  ] as const)("refuses an acknowledgement that %s, as neither success nor a stop", (_what, answer) => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_record_search_run customer_id=c idempotency_key=e1 task_id=t searches=1
printf 'status=%s\\nmetadata=%s\\n' "$?" "$UBB_STOP_REQUESTED"
`,
      { answers: [{ path: "/api/v1/metering/usage", answer }] },
    );

    expect(said(ran)).toEqual({
      status: String(SHELL_EXIT.responseUnreadable.status),
      metadata: "",
    });
    expect(ran.stderr).toContain(SHELL_MESSAGES.responseUnreadable);
  });

  it("refuses a start that is answered with no id for the work", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
ubb_start_task customer_id=c idempotency_key=w
printf 'status=%s\\ntask=%s\\n' "$?" "$UBB_TASK_ID"
`,
      { answers: [{ path: "/api/v1/tasks", answer: { raw_body: '{"status":"active"}' } }] },
    );

    expect(said(ran)).toEqual({
      status: String(SHELL_EXIT.responseUnreadable.status),
      task: "",
    });
  });
});

describe("the boundary, where no stop is met", () => {
  const boundary = (work: string, answers: RunOptions["answers"] = []) =>
    runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
work() {
${work}
}
ubb_run_task work customer_id=c idempotency_key=w
printf 'status=%s\\n' "$?"
`,
      { answers },
    );

  it.each(["1", "3", "128", "130", "143"])(
    "declares nothing for work that returned %s: the status is passed on and the Task left open, said so",
    (status) => {
      // Owner ruling on PR #598. A status is not evidence of how the work
      // went — a test that came out false leaves one — and a failed Task
      // cannot be reopened. 130 and 143 are a signal's; the rule is the same.
      const ran = boundary(`  return ${status}`);

      expect(said(ran)).toEqual({ status });
      // The start, and nothing after it: no close was sent.
      expect(ran.requests.map((request) => request.path)).toEqual(["/api/v1/tasks"]);
      expect(ran.stderr.trim()).toBe(`ubb_run_task: ${SHELL_MESSAGES.leftOpen}`);
    },
  );

  it("does not take a work function's last test coming out false for a failed Task", () => {
    // The ordinary shell construct the ruling is about: the function's last
    // command is a test, it is false, and nobody meant a failure by it.
    const ran = boundary('  ubb_record_search_run customer_id=c idempotency_key=e task_id="$1" searches=1\n  [ -n "" ] && :');

    expect(said(ran)).toEqual({ status: "1" });
    expect(ran.requests.map((request) => request.path)).toEqual([
      "/api/v1/tasks", "/api/v1/metering/usage",
    ]);
  });

  it("still sends the failure a tenant declares, as the tenant declared it", () => {
    const ran = boundary(
      '  ubb_close_task task_id="$1" outcome=failed outcome_reason=timeout || return $?\n  return 3',
    );

    expect(said(ran)).toEqual({ status: "3" });
    expect(ran.requests[1]!.body).toEqual({ outcome: "failed", outcome_reason: "timeout" });
    // Declared, so there is nothing left open to say.
    expect(ran.stderr).toBe("");
  });

  it("leaves work that ended cleanly without an outcome open, and says so", () => {
    const ran = boundary("  :");

    expect(said(ran)).toEqual({ status: String(SHELL_EXIT.usage.status) });
    expect(ran.stderr).toContain(`ubb_run_task: ${SHELL_MESSAGES.outcomeRequired}`);
    expect(ran.requests.map((request) => request.path)).toEqual(["/api/v1/tasks"]);
  });

  it("declares nothing more for work that declared its own outcome", () => {
    const failed = boundary('  ubb_close_task task_id="$1" outcome=cancelled\n  return 9');
    const delivered = boundary('  ubb_close_task task_id="$1" outcome=delivered');

    expect(said(failed)).toEqual({ status: "9" });
    expect(failed.requests.map((request) => request.body)).toEqual([
      expect.anything(), { outcome: "cancelled" },
    ]);
    expect(said(delivered)).toEqual({ status: "0" });
    expect(delivered.requests).toHaveLength(2);
  });

  it("starts nothing and runs nothing where the start itself is refused", () => {
    const ran = runShell(
      rendered("shell-direct-task-events"),
      `${SOURCE}
work() { printf 'ran=yes\\n'; }
ubb_run_task work customer_id=c
printf 'status=%s\\n' "$?"
ubb_run_task
printf 'no_work=%s\\n' "$?"
`,
    );

    expect(said(ran)).toEqual({
      status: String(SHELL_EXIT.usage.status),
      no_work: String(SHELL_EXIT.usage.status),
    });
    expect(ran.requests).toEqual([]);
  });
});

describe("a cost the supplier reports, in a shell file", () => {
  const CASES = join(FIXTURES, "reported-cost-cases.json");

  it("is converted exactly as the platform converts its text, case for case, under sh and bash", () => {
    const answer = reportedCostInShell(rendered("shell-reported-cost"), CASES);

    expect(answer.shells).toEqual(["sh", "bash"]);
    expect(answer.amounts).toBeGreaterThan(90);
    expect(answer.currencies).toBeGreaterThan(8);
    expect(answer.disagreements).toEqual([]);
  });

  it("is held to cases that refuse as well as convert, and to every spelling of a number", () => {
    const cases = JSON.parse(readFileSync(CASES, "utf-8")) as {
      amounts: {
        amount: { type: string; text: string };
        expected: { refused?: string; answer?: number };
        expected_as_text: { refused?: string; answer?: number };
      }[];
    };
    const asText = (kind: string) =>
      cases.amounts.filter((entry) => entry.expected_as_text.refused === kind).length;
    const text = (pattern: RegExp) =>
      cases.amounts.filter((entry) => pattern.test(entry.amount.text)).length;

    expect(asText("amount")).toBeGreaterThan(25);
    expect(asText("currency")).toBeGreaterThan(0);
    expect(cases.amounts.filter((entry) => "answer" in entry.expected_as_text).length).toBeGreaterThan(40);
    // An exponent, a sign, a bare point, an underscore, padding, and a
    // figure at the very edge of what a money column holds.
    for (const pattern of [/[eE]/, /^-/, /^\+/, /^\./, /\.$/, /_/, /^\s/, /^9223372036854775807$/]) {
      expect(text(pattern), String(pattern)).toBeGreaterThan(0);
    }
    // The one place the two answers part: a binary float is refused, and a
    // shell argument is text, which is the decimal it spells.
    const differ = cases.amounts.filter(
      (entry) => JSON.stringify(entry.expected) !== JSON.stringify(entry.expected_as_text),
    );
    expect(differ.map((entry) => entry.amount.type)).toEqual(["float", "float"]);
  });

  it("does no arithmetic on the amount: nothing in the file could round it", () => {
    const module = only(rendered("shell-reported-cost"), "module").contents;
    const convert = functionsOf(module).find((defined) => defined.name === "_ubb_to_micros")!;
    const arithmetic = convert.lines.flatMap((line) => line.match(/\$\(\([^)]*\)\)/g) ?? []);

    // Every arithmetic expansion is of an exponent or a count of places —
    // small whole numbers — and none names the amount or its digits.
    expect(arithmetic.length).toBeGreaterThan(2);
    for (const expansion of arithmetic) {
      expect(expansion).not.toMatch(/_ubb_(digits|text|whole|micros)\b|\$1/);
    }
    expect(convert.lines.join("\n")).not.toMatch(/\b(bc|awk|jq|expr|printf '%[df])/);
    // And the figure is written into the body by the shell, as its digits:
    // it is never a jq number.
    expect(module).not.toMatch(/--argjson p_reported_cost/);
    expect(module).toContain(
      '_ubb_body="{\\"provider_cost_micros\\":$_ubb_micros_provider_cost_micros,${_ubb_body#?}"',
    );
  });

  it("goes on the wire as whole micros, every digit of it, with the declared currency", () => {
    const ran = runShell(
      rendered("shell-reported-cost"),
      `${SOURCE}
for cost in 0.014 12.000001 9223372036854.775807 ' 1_000.5 ' 1E+3; do
  ubb_record_web_search customer_id=c idempotency_key=e task_id=t searches=1 reported_cost="$cost"
  printf 'status_%s=%s\\n' "$((count = \${count:-0} + 1))" "$?"
done
`,
    );

    expect(Object.values(said(ran))).toEqual(["0", "0", "0", "0", "0"]);
    // Read off the bytes that arrived: nineteen digits are more than the
    // numbers of the language this test is written in can hold.
    expect(
      ran.requests.map((request) => /"provider_cost_micros":(-?\d+)[,}]/.exec(request.raw)?.[1]),
    ).toEqual(["14000", "12000001", "9223372036854775807", "1000500000", "1000000000"]);
    for (const request of ran.requests) {
      expect(request.body.currency).toBe("usd");
      expect(Object.keys(request.body).sort()).toEqual([
        "currency", "customer_id", "event_type", "idempotency_key", "measurements",
        "provider", "provider_cost_micros", "task_id",
      ]);
    }
  });

  it("refuses an over-precise amount, one that is not a number and a missing one before anything is sent", () => {
    const ran = runShell(
      rendered("shell-reported-cost"),
      `${SOURCE}
for cost in 0.0000001 free 9223372036854.775808 1e41 ''; do
  ubb_record_web_search customer_id=c idempotency_key=e task_id=t searches=1 reported_cost="$cost"
  printf 'status_%s=%s\\n' "$((count = \${count:-0} + 1))" "$?"
done
`,
    );
    const refused = String(SHELL_EXIT.valueRefused.status);

    // The last is a parameter passed empty: refused as one, like any other.
    expect(Object.values(said(ran))).toEqual([
      refused, refused, refused, refused, String(SHELL_EXIT.usage.status),
    ]);
    expect(ran.stderr).toContain(`ubb_record_web_search: reported_cost ${SHELL_MESSAGES.missing}`);
    expect(ran.stderr).toContain(`0.0000001 ${MESSAGES.fractional}`);
    expect(ran.stderr).toContain(`free ${MESSAGES.notANumber}`);
    expect(ran.stderr).toContain(`9223372036854.775808 ${MESSAGES.tooLarge}`);
    expect(ran.stderr).toContain(`1e41 ${MESSAGES.exponent}`);
    expect(ran.requests).toEqual([]);
  });

  it("fails on a currency that disagrees with the declared one", () => {
    // The helper's own proof. Generated code has no supplier currency to
    // pass for a cost the caller supplies; the ticket that reads a cost off
    // the supplier's response (#583) owes the case through the artifact.
    const ran = runShell(
      rendered("shell-reported-cost"),
      `${SOURCE}
_ubb_pin_currency usd ' USD '
printf 'agrees=%s %s\\n' "$?" "$_ubb_currency"
_ubb_pin_currency usd eur
printf 'disagrees=%s\\n' "$?"
`,
    );

    expect(said(ran)).toEqual({
      agrees: "0 usd",
      disagrees: String(SHELL_EXIT.valueRefused.status),
    });
    expect(ran.stderr).toContain(`${MESSAGES.currencyDisagrees}: eur, usd`);
  });

  it("is absent from a file that reports no cost", () => {
    const module = only(rendered("shell-calculated-cost"), "module").contents;

    expect(module).not.toContain("_ubb_to_micros");
    expect(module).not.toContain("_ubb_pin_currency");
    expect(module).not.toContain("provider_cost_micros");
  });

  it("is never rendered for a cost read off the response, which stays blocked", () => {
    const record = functionsOf(only(rendered("shell-blocked"), "module").contents).filter(
      (defined) => defined.name.endsWith("record_web_search"),
    );

    // The call, and the program that is its body.
    expect(record.map((defined) => defined.name)).toEqual([
      "_ubb_jq_body_record_web_search", "ubb_record_web_search",
    ]);
    for (const defined of record) {
      expect(defined.lines.join("\n")).not.toMatch(
        /provider_cost_micros|"currency"|_ubb_to_micros/,
      );
    }
  });
});

describe("a shell file that is not ready", () => {
  it("refuses every call that is not ready, naming what is missing", () => {
    const ran = runShell(
      rendered("shell-scaffold"),
      `${SOURCE}
ubb_start_task customer_id=c idempotency_key=w
printf 'start=%s\\n' "$?"
work() { :; }
ubb_run_task work customer_id=c idempotency_key=w
printf 'work=%s\\n' "$?"
ubb_record_usage customer_id=c idempotency_key=e task_id=t
printf 'record=%s\\n' "$?"
`,
    );
    const refused = String(SHELL_EXIT.notConfigured.status);

    expect(said(ran)).toEqual({ start: refused, work: refused, record: refused });
    expect(ran.stderr).toContain(
      `api_v1_task_endpoints_start_task (scaffold) ${MESSAGES.notReady} task_type ${MESSAGES.notConfigured}.`,
    );
    expect(ran.stderr).toContain(
      `api_v1_metering_endpoints_record_usage (scaffold) ${MESSAGES.notReady} event_type ${MESSAGES.notConfigured}.`,
    );
    expect(ran.requests).toEqual([]);
  });

  it("refuses before it looks for a tool: a scaffold says what is missing on any machine", () => {
    const ran = runShell(
      rendered("shell-scaffold"),
      `PATH=/nowhere
${SOURCE}
ubb_start_task customer_id=c idempotency_key=w
printf 'start=%s\\n' "$?"
`,
    );

    expect(said(ran)).toEqual({ start: String(SHELL_EXIT.notConfigured.status) });
  });

  it("still runs the calls that are ready, and refuses the ones that are not", () => {
    const ran = runShell(
      rendered("shell-blocked"),
      `${SOURCE}
ubb_start_task customer_id=c idempotency_key=w
printf 'start=%s\\n' "$?"
for record in ubb_record_chat_completion ubb_record_draft_only ubb_record_web_search; do
  "$record" customer_id=c idempotency_key=e task_id="$UBB_TASK_ID" response=r.json searches=1
  printf '%s=%s\\n' "$record" "$?"
done
`,
    );
    const refused = String(SHELL_EXIT.notConfigured.status);

    expect(said(ran)).toEqual({
      start: "0",
      ubb_record_chat_completion: refused,
      ubb_record_draft_only: refused,
      ubb_record_web_search: refused,
    });
    expect(ran.stderr).toContain(`measurements.flat_fee ${MESSAGES.notConfigured}.`);
    expect(ran.stderr).toContain("api_v1_metering_endpoints_record_usage (blocked)");
    expect(ran.requests.map((request) => request.path)).toEqual(["/api/v1/tasks"]);
  });

  it("prints the name it refuses over whatever the name holds, and runs none of it", () => {
    // NOT a Blueprint the routes answered: the blocked fixture with its
    // constant quantity renamed to text that would end a quoted word and run
    // a command if a refusal ever wrote it into shell code unescaped.
    const key = "it's $(touch made-by-a-refusal) `touch made-by-a-backtick`\n'; touch made-by-a-quote; '";
    const blueprint = fixture("shell-blocked");
    for (const argument of everyArgument(blueprint)) {
      if (argument.name === "measurements" && argument.value === "flat_fee") argument.value = key;
      if (argument.name.startsWith("measurements.flat_fee")) {
        argument.name = argument.name.replace("measurements.flat_fee", `measurements.${key}`);
      }
    }
    const files = render(blueprint);

    expect(Object.values(parsed(files)).filter((refusal) => refusal !== null)).toEqual([]);
    const ran = runShell(
      files,
      `${SOURCE}
ubb_record_chat_completion customer_id=c idempotency_key=e task_id=t response=r.json
printf 'status=%s\\n' "$?"
ls
`,
    );

    expect(said(ran)).toEqual({ status: String(SHELL_EXIT.notConfigured.status) });
    // On one line: the newline in the name is shown as its escape.
    expect(ran.stderr).toContain(
      "measurements.it's $(touch made-by-a-refusal) `touch made-by-a-backtick`\\u000a'; touch made-by-a-quote; ' " +
        `${MESSAGES.notConfigured}.`,
    );
    expect(ran.stdout).not.toMatch(/made-by/);
    expect(ran.requests).toEqual([]);
  });

  it("refuses the record a shell file cannot read the response of, and runs the rest", () => {
    const ran = runShell(
      rendered("shell-unreadable-shape"),
      `${SOURCE}
ubb_start_task customer_id=c idempotency_key=w environment=production
printf 'start=%s\\n' "$?"
ubb_record_chat_completion customer_id=c idempotency_key=e task_id=t response=r.json searches=1
printf 'record=%s\\n' "$?"
`,
    );

    expect(said(ran)).toEqual({ start: "0", record: String(SHELL_EXIT.notConfigured.status) });
    // Naming the two quantities it has no way to read.
    expect(ran.stderr).toContain(
      `measurements.input_tokens ${MESSAGES.notConfigured}. measurements.output_tokens ${MESSAGES.notConfigured}.`,
    );
    expect(ran.requests).toHaveLength(1);
  });

  it("states a quantity no token gives a value to, and sends nothing for it", () => {
    const module = only(rendered("shell-blocked"), "module").contents;

    expect(module).toContain('# measurements = "ratio" · event_type "chat.completion"');
    expect(module).not.toMatch(/"ratio":/);
  });
});

describe("declared names, in a shell file", () => {
  const ODD = [
    "it's", "$HOME", "$(whoami)", "back`tick", "back\\slash", 'dou"ble',
    "naïve–日本語", "cache-read", "cache read tokens", "per.cent%", "{braces}",
    "class",
  ];

  it("reach the wire exactly as they were declared", () => {
    const { ran } = runLifecycle("shell-odd-names");

    expect(said(ran), ran.stderr).toEqual({ status: "0" });
    const [start, record] = ran.requests;
    expect(start!.body.task_type).toBe("report-generation");
    expect(record!.body.event_type).toBe("it's a $5 chat-completion");
    expect(record!.body.provider).toBe("o'reilly & co");
    expect(record!.body.measurements).toEqual({
      ...Object.fromEntries(ODD.map((code) => [code, 3])),
      "read off a hyphenated key": 7,
    });
  });

  /**
   * NOT a Blueprint the routes answered: the odd-names fixture with one
   * declared name, and every token named under it, replaced by text that
   * would end a heredoc, a string, a jq program or a line if it were ever
   * written unescaped — and by text that would run a command if anything
   * expanded it. Whether a registry admits such a name is the registry's
   * business; that the renderer survives one is the renderer's.
   */
  function hostile(key: string): ResolvedIntegrationBlueprint {
    const blueprint = fixture("shell-odd-names");
    for (const argument of everyArgument(blueprint)) {
      if (argument.name === "measurements" && argument.value === "class") argument.value = key;
      if (argument.name.startsWith("measurements.class")) {
        argument.name = argument.name.replace("measurements.class", `measurements.${key}`);
      }
      if (argument.name === "event_type") {
        argument.value = `${argument.value}\r\nUBB_JQ\n$(touch made-by-an-event-type)`;
      }
      if (argument.provenance?.object_kind === "event_type") {
        argument.provenance.key = `${argument.provenance.key}\r\nUBB_JQ\n$(touch made-by-an-event-type)`;
      }
    }
    return blueprint;
  }

  const HOSTILE: [string, string][] = [
    ["the heredoc's own delimiter", "UBB_JQ"],
    ["the delimiter on a line of its own", "x\nUBB_JQ\ny"],
    [
      "a quote, a newline, a command, a backtick, jq's interpolation and a line separator",
      `x"\n  $(touch made-by-a-key) \`touch made-by-a-backtick\` \\(1 + 1) ${String.fromCharCode(0x2028)} \\`,
    ],
    ["an apostrophe that would end a quoted word", "'; touch made-by-a-quote; '"],
  ];

  it.each(HOSTILE)("cannot end a heredoc, a string or a line, or run anything: %s", (_what, key) => {
    const blueprint = hostile(key);
    const files = render(blueprint);
    const module = only(files, "module").contents;

    expect(Object.values(parsed(files)).filter((refusal) => refusal !== null)).toEqual([]);
    // The only lines that are the delimiter are the ones that end a heredoc.
    expect(module.split("\n").filter((line) => line.trim() === SHELL_FILE.heredoc)).toHaveLength(
      heredocs(module).filter((heredoc) => heredoc.delimiter === SHELL_FILE.heredoc).length,
    );
    const lineEnders = [0x0085, 0x2028, 0x2029, 0x000b, 0x000c, 0x000d].map((unit) =>
      String.fromCharCode(unit),
    );
    for (const file of files) {
      // Nothing that could end a line is written raw, in code or in a comment.
      for (const character of lineEnders) expect(file.contents).not.toContain(character);
    }

    const { script, environment } = lifecycle(blueprint, files);
    const ran = runShell(files, `${script}\nls`, { environment });

    expect(said(ran), ran.stderr).toEqual({ status: "0" });
    expect(Object.keys(ran.requests[1]!.body.measurements as object)).toContain(key);
    expect(ran.requests[1]!.body.event_type).toBe(
      "it's a $5 chat-completion\r\nUBB_JQ\n$(touch made-by-an-event-type)",
    );
    // Nothing a name held was run.
    expect(ran.stdout).not.toMatch(/made-by/);
  });

  /**
   * NOT a Blueprint the routes answered either: the reported-cost fixture
   * with its caller-supplied quantity's parameter renamed to a name the
   * shell, jq or the file itself already gives a meaning to.
   */
  it.each([
    "PATH", "IFS", "HOME", "PWD", "OPTIND", "status", "then", "end", "reduce",
    "_ubb_body", "_ubb_p_customer_id", "UBB_TASK_ID", "UBB_EXIT_STOP_REQUESTED", "p_customer_id",
  ])("can never stand in front of a name the shell, jq or the file already has: %s", (parameter) => {
    const blueprint = fixture("shell-reported-cost");
    for (const argument of everyArgument(blueprint)) {
      if (argument.parameter_name === "searches") argument.parameter_name = parameter;
    }
    const files = render(blueprint);

    const ran = runShell(
      files,
      `${SOURCE}
before="$PATH|$HOME|$PWD|$UBB_EXIT_STOP_REQUESTED"
ubb_record_web_search customer_id=c idempotency_key=e task_id=t reported_cost=1.5 ${parameter}=7
printf 'status=%s\\n' "$?"
[ "$before" = "$PATH|$HOME|$PWD|$UBB_EXIT_STOP_REQUESTED" ] && printf 'untouched=yes\\n'
`,
    );

    expect(said(ran), ran.stderr).toEqual({ status: "0", untouched: "yes" });
    expect(ran.requests.map((request) => request.body.measurements)).toEqual([{ searches: 7 }]);
    expect(ran.requests[0]!.body.customer_id).toBe("c");
    expect(ran.requests[0]!.raw).toContain('"provider_cost_micros":1500000,');
  });

  it("name each function for its declared key, by the rule the Python target names its own", () => {
    const names = (files: RenderedFile[]) =>
      functionsOf(only(files, "module").contents)
        .map((defined) => defined.name)
        .filter((name) => name.startsWith("ubb_record_"));
    const python = (files: RenderedFile[]) => {
      const module = only(files, "module").contents;
      return [...module.matchAll(/^def (record_\w+)/gm)].map((match) => match[1]!);
    };

    expect(names(rendered("shell-direct-task-events"))).toEqual([
      "ubb_record_reply_sent", "ubb_record_search_run",
    ]);
    // The same tails as the Python file of the same selection.
    for (const branch of ["direct-task-events", "odd-names", "explicit-subtasks", "scaffold"]) {
      expect(names(rendered(`shell-${branch}`))).toEqual(
        python(rendered(branch)).map((name) => `ubb_${name}`),
      );
    }
  });

  it("never share a function between two keys, and give neither the plain name", () => {
    const blueprint = fixture("shell-direct-task-events");
    // Two Event Types whose keys differ only where a function name cannot.
    for (const argument of everyArgument(blueprint)) {
      if (argument.name === "event_type" && argument.value === "reply.sent") {
        argument.value = "search-run";
      }
    }
    const colliding = functionsOf(only(render(blueprint), "module").contents)
      .map((defined) => defined.name)
      .filter((name) => name.startsWith("ubb_record_"));

    expect(new Set(colliding).size).toBe(2);
    // Neither keeps the plain name: a function a call site already uses is
    // never silently handed to another Event Type.
    expect(colliding).not.toContain("ubb_record_search_run");
    expect(colliding.every((name) => /^ubb_record_search_run_[0-9a-f]{8}$/.test(name))).toBe(true);
  });
});

describe("the shell verify script", () => {
  function verify(branch: string, eventType: string | null, captured: unknown, files = rendered(branch)) {
    const ran = runShell(
      files,
      `printf '%s' "$CAPTURED" >captured.json
${eventType === null ? "sh verify_integration.sh" : 'sh verify_integration.sh "$EVENT_TYPE" captured.json'}
printf 'status=%s\\n' "$?"
`,
      { environment: { CAPTURED: JSON.stringify(captured), EVENT_TYPE: eventType ?? "" } },
    );
    return { status: Number(said(ran).status), output: ran.stdout + ran.stderr, requests: ran.requests };
  }

  it("passes a captured response every declared path resolves in", () => {
    const answer = verify("shell-calculated-cost", "chat.completion", {
      usageMetadata: { promptTokenCount: 1200, candidatesTokenCount: 340 },
    });

    expect(answer.output).toContain(`  ${MESSAGES.verifyOk} "input_tokens" ${MESSAGES.verifyResolves}`);
    expect(answer.output).toContain(MESSAGES.verifyPassed);
    expect(answer.status).toBe(0);
  });

  it("fails on a path that does not resolve", () => {
    const answer = verify("shell-calculated-cost", "chat.completion", {
      usageMetadata: { promptTokenCount: 1200 },
    });

    expect(answer.status).toBe(1);
    expect(answer.output).toMatch(/FAIL "output_tokens" resolves/);
    expect(answer.output).toContain(`1 ${MESSAGES.verifyFailed}`);
  });

  it("fails on a quantity that reads a constant zero", () => {
    const answer = verify("shell-calculated-cost", "chat.completion", {
      usageMetadata: { promptTokenCount: 0, candidatesTokenCount: 340 },
    });

    expect(answer.status).toBe(1);
    expect(answer.output).toMatch(/FAIL "input_tokens" is not zero/);
  });

  it("fails on a value that is not a number, a present null among them", () => {
    const answer = verify("shell-calculated-cost", "chat.completion", {
      usageMetadata: { promptTokenCount: "1200", candidatesTokenCount: null },
    });

    expect(answer.status).toBe(1);
    expect(answer.output).toMatch(/FAIL "input_tokens" is a number/);
    // Present and null is found, and is not a number: not the same as absent.
    expect(answer.output).toMatch(/ok {3}"output_tokens" resolves/);
    expect(answer.output).toMatch(/FAIL "output_tokens" is a number/);
  });

  it("fails on two quantities read from one field", () => {
    // NOT a Blueprint the routes answered: the second quantity's declared
    // path is pointed at the first one's field.
    const blueprint = fixture("shell-calculated-cost");
    for (const argument of everyArgument(blueprint)) {
      if (argument.name === "measurements.output_tokens.source_path") {
        argument.value = ["usageMetadata", "promptTokenCount"];
      }
    }

    const answer = verify(
      "shell-calculated-cost",
      "chat.completion",
      { usageMetadata: { promptTokenCount: 1200, candidatesTokenCount: 340 } },
      render(blueprint),
    );

    expect(answer.status).toBe(1);
    expect(answer.output).toMatch(/FAIL "output_tokens" is read from a path no other quantity/);
  });

  it("walks a declared name of any spelling, and calls nothing", () => {
    const answer = verify("shell-odd-names", "it's a $5 chat-completion", {
      "x-usage": { "total tokens": 99 },
    });

    expect(answer.output).toContain(MESSAGES.verifyPassed);
    expect(answer.status).toBe(0);
    expect(answer.requests).toEqual([]);
    expect(only(rendered("shell-odd-names"), "verify_script").contents).not.toMatch(/\bcurl\b/);
  });

  it("says so, and exits clean, where no selected Event Type reads a response", () => {
    const answer = verify("shell-direct-task-events", "reply.sent", {});

    expect(answer.output).toContain(MESSAGES.verifyNothing);
    expect(answer.status).toBe(0);
  });

  it("names the Event Types it knows when asked for one it does not, or for none", () => {
    const unknown = verify("shell-calculated-cost", "something.else", {});
    const none = verify("shell-calculated-cost", null, {});

    for (const answer of [unknown, none]) {
      expect(answer.status).toBe(2);
      expect(answer.output).toContain(SHELL_MESSAGES.verifyUsage);
      expect(answer.output).toContain('  "chat.completion"');
    }
  });
});

describe("the two ways a jq program can arrive through a quoted heredoc", () => {
  // The decision #180 §12.1 left open, made by running both. Each form is a
  // committed script of its own, over the same names; the renderer writes
  // the first, and the second is kept as what it was decided against.
  const form = (name: string) =>
    readFileSync(join(PACKAGE_ROOT, "tests", "harness", `${name}.sh`), "utf-8");
  const FORMS = {
    "from standard input": form("heredoc_from_standard_input"),
    "as an argument": form("heredoc_as_an_argument"),
  };
  const EXPECTED = {
    "it's": "it's",
    "$HOME": "$HOME",
    "$(touch made-by-a-name)": "$(touch made-by-a-name)",
    "back`tick": "back`tick",
    "back\\slash\\n": "back\\slash\\n",
    "naïve–日本語": "naïve–日本語",
    "cache-read": "cache-read",
    "cache read tokens": "cache read tokens",
    "unbalanced)": "unbalanced)",
    UBB_JQ: "UBB_JQ",
  };

  it.each(
    (["sh", "bash"] as const).flatMap((shell) =>
      Object.keys(FORMS).map((name) => [name, shell] as const),
    ),
  )("%s, a program carries every kind of name unchanged, expands nothing and runs nothing (%s)", (name, shell) => {
    const ran = runShell([], FORMS[name as keyof typeof FORMS], { shell });
    const answers = said(ran);

    expect(ran.stderr).toBe("");
    expect(JSON.parse(answers.carried!)).toEqual(EXPECTED);
    expect(answers.ran_anything).toBe("no");
  });

  it("differ in one thing: only the form decided against opens a heredoc inside a substitution", () => {
    // Which is what bash 3.2 cannot parse once a name holds one backtick —
    // recorded, with the command that shows it, at the head of that script.
    const inside = (script: string) =>
      substitutions(script).filter((substitution) => substitution.includes("<<"));

    expect(inside(FORMS["as an argument"])).toHaveLength(1);
    expect(inside(FORMS["from standard input"])).toEqual([]);
    // Both are run over a name that holds exactly one.
    for (const script of Object.values(FORMS)) {
      expect(script).toContain("backtick='back`tick'");
    }
  });

  it("is settled the way the rendered file is written", () => {
    const module = only(rendered("shell-odd-names"), "module").contents;

    expect(module).toContain("--from-file /dev/stdin <<'UBB_JQ'");
    // No program is handed to jq as an argument: not inline, and not as the
    // output of another command.
    expect(module).not.toMatch(/\$\(cat <</);
    expect(module).not.toMatch(/jq [^\n]*'\{/);
    // And the branch it is settled over holds a name with one backtick.
    expect(module).toContain('"back`tick"');
  });
});
