/**
 * What a rendered shell artifact is, read off the text `render` returns
 * (#578).
 *
 * The files, the header, the two classes of comment, the shapes a value
 * takes, the rule that the lines a tenant maintains carry no generated value,
 * and the structural rules of the Shell / raw HTTP target: every jq program
 * in a quoted heredoc, every runtime value an argument, no function run in a
 * subshell, no `exit`. `sh` and `bash` answer whether a file parses; what is
 * a heredoc, a substitution or a function is read off the text by this
 * suite's own readers, never by the renderer's.
 */
import { describe, expect, it } from "vitest";

import {
  BlueprintNotRenderable,
  COMMENTS,
  ENVIRONMENT,
  PRICING_MODE_COMMENTS,
  REMEDIATION,
  render,
  SHELL,
  SHELL_COMMENTS,
  SHELL_EXIT,
  SHELL_FILE,
  SHELL_READINESS_COMMENTS,
  type RenderedFile,
} from "../src/index.ts";
import type { ResolvedIntegrationBlueprint } from "../src/blueprint.ts";
import { everyArgument, fixture } from "./support/fixtures.ts";
import {
  BRANCHES,
  commentText,
  hashComments,
  only,
  PLANTED,
  provenanceOf,
  rendered,
  SHELL_BRANCH_NAMES,
} from "./support/rendered.ts";
import { parsed } from "./support/shell.ts";
import {
  functionsOf,
  heredocs,
  jqCode,
  parametersOf,
  shellCode,
  substitutions,
} from "./support/shellText.ts";

/** The members of the shared catalogue a shell file carries: the ones that
 * are true of any target. Listed here, not read off the renderer. */
const SHARED = [
  COMMENTS.generated, COMMENTS.draftPreview, COMMENTS.fingerprint, COMMENTS.resolvedFrom,
  COMMENTS.noDiagnostics, COMMENTS.diagnostics, COMMENTS.remediationRequest,
  COMMENTS.apiKey, COMMENTS.baseUrl, COMMENTS.notReadyCall, COMMENTS.start,
  COMMENTS.subtask, COMMENTS.environmentFile, COMMENTS.verifyPaths,
  COMMENTS.callSiteSubtask,
];

const CATALOGUE_LINES = new Set<string>([
  ...SHARED.flat(),
  ...[SHELL_COMMENTS, SHELL_READINESS_COMMENTS, REMEDIATION, PRICING_MODE_COMMENTS].flatMap(
    (group) => Object.values(group).flat(),
  ),
]);

function moduleOf(branch: string): RenderedFile {
  return only(rendered(branch), "module");
}

function of(branch: string, kind: RenderedFile["kind"]): RenderedFile[] {
  return rendered(branch).filter((file) => file.kind === kind);
}

/** Every comment of every file of a branch, as its text. */
function comments(branch: string): string[] {
  return rendered(branch).flatMap((file) => hashComments(file.contents).map(commentText));
}

/** A block's lines that are not comments. */
function blockLines(file: RenderedFile): string[] {
  return file.contents.split("\n").filter((line) => line !== "" && !line.startsWith("#"));
}

describe.each(SHELL_BRANCH_NAMES)("the %s artifact", (branch) => {
  it("is one runnable file, its call-site blocks, an environment example, a verify script and a preview of each request", () => {
    const files = rendered(branch);
    const blueprint = BRANCHES[branch]!();

    expect(of(branch, "module").map((file) => file.path)).toEqual(["ubb_integration.sh"]);
    expect(of(branch, "environment_example").map((file) => file.path)).toEqual([".env.example"]);
    expect(of(branch, "verify_script").map((file) => file.path)).toEqual([
      "verify_integration.sh",
    ]);
    expect(of(branch, "call_site").length).toBeGreaterThan(3);
    // One preview a call, and the Blueprint is where the calls are counted.
    expect(of(branch, "request_preview")).toHaveLength(blueprint.calls.length);
    expect(new Set(files.map((file) => file.path)).size).toBe(files.length);
    for (const file of files) {
      expect(file.contents.endsWith("\n"), file.path).toBe(true);
      expect(file.contents.includes("\r"), file.path).toBe(false);
    }
  });

  it("parses, every shell file of it, under sh and under bash", () => {
    const answers = parsed(rendered(branch));

    expect(Object.keys(answers).length).toBeGreaterThan(5);
    expect(Object.entries(answers).filter(([, refusal]) => refusal !== null)).toEqual([]);
  });

  it("carries only comments that are provenance or a catalogue member", () => {
    const found = comments(branch);
    const neither = found.filter(
      (text) => !CATALOGUE_LINES.has(text) && provenanceOf(text) === null,
    );

    expect(found.length).toBeGreaterThan(40);
    expect(neither).toEqual([]);
  });

  it("states in a provenance comment only what the Blueprint carries", () => {
    const blueprint = BRANCHES[branch]!();
    const carried = new Set<string>();
    const add = (name: string, value: unknown) =>
      carried.add(`${name}=${JSON.stringify(value)}`);
    for (const [field, value] of Object.entries(blueprint)) {
      if (field !== "calls" && field !== "diagnostics") add(field, value);
    }
    for (const call of blueprint.calls) add("operation_id", call.operation_id);
    for (const argument of everyArgument(blueprint)) {
      if (argument.binding_class === "platform_known" && argument.configured) {
        add(argument.name, argument.value);
      }
      if (argument.provenance) {
        add(argument.provenance.object_kind, argument.provenance.key);
        add("published_revision", argument.provenance.published_revision);
        add("published_at", argument.provenance.published_at);
      }
    }
    for (const diagnostic of blueprint.diagnostics) {
      add("diagnostic", diagnostic.code);
      add("severity", diagnostic.severity);
      add(diagnostic.object_kind, diagnostic.key ?? null);
      add("field", diagnostic.field ?? null);
      add("remediation_request", diagnostic.remediation_request ?? null);
    }

    const stated = comments(branch)
      .filter((text) => !CATALOGUE_LINES.has(text))
      .map((text) => provenanceOf(text)!)
      .flatMap((statement) => [
        `${statement.name}=${JSON.stringify(statement.value)}`,
        ...statement.qualifiers.map(
          ([qualifier, value]) => `${qualifier}=${JSON.stringify(value)}`,
        ),
      ]);

    expect(stated.length).toBeGreaterThan(8);
    expect(stated.filter((statement) => !carried.has(statement))).toEqual([]);
  });

  it("puts no generated value in a call-site block", () => {
    const blocks = of(branch, "call_site");

    expect(blocks.length).toBeGreaterThan(3);
    for (const block of blocks) {
      // With every expansion of a variable taken out, a block holds no
      // quoted text and no number: nothing a change of configuration could
      // make stale.
      const without = blockLines(block)
        .join("\n")
        .replace(/"\$[A-Za-z_?][A-Za-z0-9_]*"/g, "")
        .replace(/\$[A-Za-z_?1][A-Za-z0-9_]*/g, "");
      expect(without, block.path).not.toMatch(/["'`]/);
      expect(without.replace(/[A-Za-z_][A-Za-z0-9_]*/g, ""), block.path).not.toMatch(/[0-9]/);
    }
  });

  it("names nothing in a call-site block but the file's functions, parameters and the work", () => {
    const blueprint = BRANCHES[branch]!();
    const allowed = new Set([
      ...functionsOf(moduleOf(branch).contents)
        .map((defined) => defined.name)
        .filter((name) => !name.startsWith("_")),
      ...everyArgument(blueprint).flatMap((argument) =>
        argument.parameter_name ? [argument.parameter_name] : [],
      ),
      "work", "task_id", "subtask_id",
      SHELL.stopExitStatusName, SHELL_FILE.taskId,
      "if", "then", "fi", "return", "eq",
    ]);

    for (const block of of(branch, "call_site")) {
      const names = blockLines(block).join("\n").match(/[A-Za-z_][A-Za-z0-9_]*/g) ?? [];
      expect(names.filter((name) => !allowed.has(name)), block.path).toEqual([]);
    }
  });

  it("writes every platform-known value a call sends as the JSON that means it", () => {
    const blueprint = BRANCHES[branch]!();
    const programs = heredocs(moduleOf(branch).contents).flatMap((heredoc) => heredoc.body);
    const all = everyArgument(blueprint);
    // A declared key is sent where a token gives it a value: the one named
    // with two segments, directly under it. A key with none is only stated.
    const hasAValue = (index: number) => {
      for (let next = index + 1; next < all.length; next += 1) {
        const segments = all[next]!.name.split(".");
        if (segments.length === 1 || segments[0] !== all[index]!.name) return false;
        if (segments.length === 2) return true;
      }
      return false;
    };
    const sent = all.filter(
      (argument, index) =>
        argument.binding_class === "platform_known" &&
        argument.configured &&
        !argument.name.includes(".") &&
        typeof argument.value === "string" &&
        (!["grouping_fields", "measurements"].includes(argument.name) || hasAValue(index)),
    );
    expect(sent.length).toBeGreaterThanOrEqual(branch === "shell-scaffold" ? 0 : 1);

    for (const argument of sent) {
      const literal = JSON.stringify(argument.value);
      expect(programs.some((line) => line.includes(literal)), argument.name).toBe(true);
    }
  });

  it("asks for every runtime value as a name=value parameter, at the call it is declared for", () => {
    const blueprint = BRANCHES[branch]!();
    const taken = functionsOf(moduleOf(branch).contents)
      .filter((defined) => defined.name.startsWith("ubb_"))
      .map((defined) => parametersOf(defined).sort().join(","));

    for (const call of blueprint.calls) {
      const asked = new Set(
        call.arguments.flatMap((argument) =>
          argument.binding_class === "runtime_bound" ? [argument.parameter_name!] : [],
        ),
      );
      // A close may also say why work failed: the two fields its request
      // publishes beside the outcome.
      if (call.operation_id.endsWith("close_task")) {
        asked.add("outcome_reason");
        asked.add("reason_detail");
      }
      expect(taken, call.operation_id).toContain([...asked].sort().join(","));
    }
  });

  it("holds an empty assignment for each environment variable and no value", () => {
    const assignments = only(rendered(branch), "environment_example")
      .contents.split("\n")
      .filter((line) => line !== "" && !line.startsWith("#"));

    expect(assignments).toEqual([`${ENVIRONMENT.apiKey}=`, `${ENVIRONMENT.baseUrl}=`]);
  });

  it("gives every secret reference its setup instructions", () => {
    const lines = only(rendered(branch), "environment_example").contents.split("\n");
    const at = lines.indexOf(`${ENVIRONMENT.apiKey}=`);

    expect(lines.slice(at - COMMENTS.apiKey.length, at)).toEqual(
      COMMENTS.apiKey.map((line) => `# ${line}`),
    );
  });

  it("reads the credential from the environment, hands it to curl on standard input, and writes it nowhere", () => {
    const code = shellCode(moduleOf(branch).contents);
    const sending = code.filter((line) => line.includes(`$${ENVIRONMENT.apiKey}`));

    // Read in exactly one place besides the check that it is set, and there
    // it is printf's argument — a builtin — piped to curl, which reads its
    // headers from standard input. Never a word of curl's own command line.
    expect(sending).toHaveLength(1);
    expect(sending[0]).toMatch(/\$\(printf 'Authorization: Bearer %s\\n' "\$UBB_API_KEY" \| curl \\$/);
    expect(code.join("\n")).toContain("--header @-");
    for (const file of rendered(branch)) {
      expect(file.contents).not.toContain(PLANTED);
    }
  });

  it("never exits the shell that sources it, and sets none of its options", () => {
    const code = shellCode(moduleOf(branch).contents);

    expect(code.filter((line) => /(^|[\s;&|({])exit(\s|;|$)/.test(line))).toEqual([]);
    // `set --` writes a function's own arguments; anything else is an option.
    expect(code.filter((line) => /(^|[\s;&|({])set\s/.test(line) && !/\bset -- /.test(line))).toEqual(
      [],
    );
    expect(code.filter((line) => /\b(shopt|setopt|trap)\b/.test(line))).toEqual([]);
  });

  it("holds no variable of its own that is not spelled UBB_ or _ubb_", () => {
    // Every assignment: a `name=` where a command would start. A `name=`
    // later on a line is an argument a call is passed, and `name=*)` is the
    // pattern that reads one; neither assigns anything.
    const assigned = shellCode(moduleOf(branch).contents)
      .join("\n")
      .replace(/\\\n\s*/g, " ")
      .replace(/'[^'\n]*'/g, "''")
      .split("\n")
      .flatMap((line) =>
        [...line.matchAll(/(?:^\s*|[;{(]\s*|\b(?:then|do|else)\s+)([A-Za-z_][A-Za-z0-9_]*)=(?!\*\))/g)].map(
          (match) => match[1]!,
        ),
      );

    expect(assigned.length).toBeGreaterThan(20);
    expect(assigned.filter((name) => !/^(UBB_|_ubb_)/.test(name))).toEqual([]);
  });

  it("runs nothing in a subshell but a jq program and curl, and opens no heredoc in one", () => {
    const module = moduleOf(branch).contents;
    const defined = functionsOf(module);
    const programs = defined.filter((each) => each.name.startsWith("_ubb_jq_"));
    const others = defined
      .filter((each) => !each.name.startsWith("_ubb_jq_"))
      .map((each) => each.name);
    const run = substitutions(module);

    expect(others.length).toBeGreaterThan(8);
    expect(programs.length).toBeGreaterThan(3);
    expect(run).toHaveLength(programs.length + 1);
    for (const inside of run) {
      // A heredoc inside a substitution is read as shell by bash 3.2: one
      // backtick in a declared name would end the file there.
      expect(inside, inside).not.toContain("<<");
      // What a substitution runs is one function that is a jq program, or
      // the credential piped to curl.
      expect(inside.trim(), inside).toMatch(
        /^(_ubb_jq_[a-z0-9_]+( "\$1")?$|printf 'Authorization: Bearer %s\\n' "\$UBB_API_KEY" \| curl \\\n)/,
      );
      // And no other function of this file, on the stop's path or off it:
      // what one sets, and the status it returns, are its caller's to see.
      const called = others.filter((name) =>
        new RegExp(`(^|[\\s;|&(])${name}(\\s|$|;|\\))`).test(inside),
      );
      expect(called, inside).toEqual([]);
    }
    // A program function is that: one jq command with its program on
    // standard input, and nothing a caller could miss by not seeing it run.
    for (const each of programs) {
      const opener = each.lines.findIndex((line) => line.endsWith(`<<'${SHELL_FILE.heredoc}'`));
      expect(each.lines[1], each.name).toMatch(/^ {2}jq --/);
      expect(opener, each.name).toBeGreaterThan(0);
      expect(each.lines.slice(1, opener).filter((line) => !line.endsWith(" \\"))).toEqual([]);
      expect(each.lines.filter((line) => line === SHELL_FILE.heredoc), each.name).toHaveLength(1);
      expect(each.lines.slice(-2), each.name).toEqual([SHELL_FILE.heredoc, "}"]);
    }
    // Nor is a function ever run in a pipeline, which is a subshell as well.
    const piped = shellCode(module).filter((line) =>
      defined.some(({ name }) =>
        new RegExp(`(\\b${name}\\b[^|]*[^|]\\|[^|])|([^|]\\|\\s*${name}\\b)`).test(line),
      ),
    );
    expect(piped).toEqual([]);
  });

  it("holds every jq program in a quoted heredoc, no line of which could end it", () => {
    for (const file of [moduleOf(branch), only(rendered(branch), "verify_script")]) {
      const programs = heredocs(file.contents).filter(
        (heredoc) => heredoc.delimiter === SHELL_FILE.heredoc,
      );
      const code = shellCode(file.contents).join("\n");
      // Every time jq is run, it is handed its program on standard input,
      // from a heredoc: no program is an argument, quoted inline.
      const runs = code.match(/(^|[\s(])jq --/gm) ?? [];

      expect(programs.length, file.path).toBeGreaterThan(1);
      expect(runs.length, file.path).toBe(programs.length);
      // And never from inside a command substitution, in either file.
      expect(substitutions(file.contents).filter((inside) => inside.includes("<<"))).toEqual([]);
      expect(code.match(/--from-file \/dev\/stdin( >\/dev\/null 2>&1)? <<'UBB_JQ'/g)).toHaveLength(
        programs.length,
      );
      for (const program of programs) {
        // Quoted, so the shell expands nothing inside it.
        expect(program.quoted, program.opener).toBe(true);
        expect(program.body.length).toBeGreaterThan(0);
        // Every line indented, and the delimiter is not: whatever a line is
        // generated from, it is not the line that ends the heredoc.
        expect(program.body.filter((line) => !line.startsWith("  "))).toEqual([]);
      }
    }
  });

  it("passes every runtime value to jq as an argument, and quotes every key", () => {
    const module = moduleOf(branch).contents;
    const code = shellCode(module).join("\n").replace(/\\\n\s*/g, " ");
    const commands = code.match(/jq --[^\n]*<<'UBB_JQ'/g) ?? [];
    const programs = heredocs(module).filter((heredoc) => heredoc.delimiter === SHELL_FILE.heredoc);
    expect(commands).toHaveLength(programs.length);

    programs.forEach((program, index) => {
      const text = jqCode(program.body);
      const bound = [
        ...commands[index]!.matchAll(/--(?:arg|argjson|slurpfile) ([A-Za-z_][A-Za-z0-9_]*) /g),
      ].map((match) => match[1]!);
      // Names a program gives a value itself: `as $x` and a function's own
      // parameters.
      const own = [
        ...text.matchAll(/\bas \$([A-Za-z_][A-Za-z0-9_]*)/g),
        ...text.matchAll(/def [a-z_]+\(([^)]*)\)/g),
      ].flatMap((match) => match[1]!.split(";").map((name) => name.trim().replace(/^\$/, "")));
      const used = [...text.matchAll(/\$([A-Za-z_][A-Za-z0-9_]*)/g)].map((match) => match[1]!);

      // Every variable a program reads was handed to jq as an argument, or
      // is one the program made: none is shell text written into it.
      expect(used.filter((name) => !bound.includes(name) && !own.includes(name)), text).toEqual([]);
      expect(bound.filter((name) => !used.includes(name)), commands[index]).toEqual([]);
      // A key of an object is always a quoted string, never a bare word.
      expect(text.match(/[{,]\s*[A-Za-z_][A-Za-z0-9_]*\s*:/g) ?? [], text).toEqual([]);
    });
  });

  it("gives a parameter no name the shell or jq could already have a meaning for", () => {
    const module = moduleOf(branch).contents;
    const code = shellCode(module).join("\n");
    const blueprint = BRANCHES[branch]!();
    const named = new Set(
      everyArgument(blueprint).flatMap((argument) =>
        argument.binding_class === "runtime_bound" ? [argument.parameter_name!] : [],
      ),
    );

    // Held in the shell behind a prefix: the variable is never the bare name.
    expect(named.size).toBeGreaterThan(2);
    for (const name of named) expect(code).toContain(`_ubb_p_${name}=`);
    // And bound in jq behind another, whatever the name is: a value held in
    // `_ubb_p_<name>` reaches a program as `$p_<name>` and as nothing else.
    const bound = [
      ...code.matchAll(/--(?:arg|argjson|slurpfile) ([A-Za-z_][A-Za-z0-9_]*) "\$_ubb_p_([A-Za-z_][A-Za-z0-9_]*)"/g),
    ];
    expect(bound.length).toBeGreaterThan(2);
    expect(bound.filter((match) => match[1] !== `p_${match[2]}`)).toEqual([]);
    expect(bound.filter((match) => !named.has(match[2]!) &&
      !["outcome_reason", "reason_detail"].includes(match[2]!))).toEqual([]);
  });
});

describe("the header of a shell file", () => {
  function header(branch: string): string[] {
    const lines = moduleOf(branch).contents.split("\n");
    return lines.slice(0, lines.findIndex((line) => /^[A-Z_]+=/.test(line))).map(commentText);
  }

  it("states the three versions, the target, the fingerprint and the verdict", () => {
    const blueprint = fixture("shell-calculated-cost");

    expect(header("shell-calculated-cost")).toEqual(
      expect.arrayContaining([
        "schema_version = 1",
        "renderer_contract_version = 1",
        // No SDK stands between a shell file and the API, and none is claimed.
        "sdk_major_version = null",
        'target = "shell_http"',
        `configuration_fingerprint = "${blueprint.configuration_fingerprint}"`,
        'readiness = "complete"',
        ...SHELL_READINESS_COMMENTS.complete,
      ]),
    );
  });

  it("states each Event Type's revision and the date it was published", () => {
    expect(header("shell-direct-task-events")).toEqual(
      expect.arrayContaining([
        'event_type = "reply.sent" · published_revision 1 · published_at "2026-09-01T12:00:00+00:00"',
        'event_type = "search.run" · published_revision 1 · published_at "2026-09-01T12:00:00+00:00"',
        'task_type = "support_reply"',
      ]),
    );
  });

  it.each(["scaffold", "blocked"] as const)(
    "states a %s verdict and what it means for a shell file",
    (readiness) => {
      expect(header(`shell-${readiness}`)).toEqual(
        expect.arrayContaining([
          `readiness = "${readiness}"`,
          ...SHELL_READINESS_COMMENTS[readiness],
        ]),
      );
      // Not in the words of another target: nothing here raises an exception.
      expect(header(`shell-${readiness}`).join("\n")).not.toContain("UBBIntegrationNotReady");
    },
  );

  it("lists every diagnostic with its remediation and the request that fixes it", () => {
    const blueprint = fixture("shell-blocked");
    const lines = header("shell-blocked");

    expect(blueprint.diagnostics.length).toBeGreaterThan(4);
    for (const diagnostic of blueprint.diagnostics) {
      const at = lines.indexOf(
        `diagnostic = "${diagnostic.code}" · severity "${diagnostic.severity}"` +
          ` · ${diagnostic.object_kind} ${JSON.stringify(diagnostic.key)}` +
          ` · field ${JSON.stringify(diagnostic.field)}`,
      );
      expect(at, diagnostic.code).toBeGreaterThan(-1);
      const after = lines.slice(at + 1, at + 1 + REMEDIATION[diagnostic.code].length);
      expect(after).toEqual(REMEDIATION[diagnostic.code]);
      expect(lines).toContain(
        `remediation_request = ${JSON.stringify(diagnostic.remediation_request)}`,
      );
    }
  });

  it("says a response shape this target cannot read is why the file is blocked", () => {
    const lines = header("shell-unreadable-shape");

    expect(lines).toContain('readiness = "blocked"');
    expect(
      lines.filter((line) => line.startsWith("diagnostic = ")).map((line) => line.split(" · ")[0]),
    ).toEqual(['diagnostic = "response_shape_not_readable_by_target"']);
    expect(lines).toEqual(
      expect.arrayContaining([...REMEDIATION.response_shape_not_readable_by_target]),
    );
  });

  it("says a draft preview is one, and claims no fingerprint and no publication", () => {
    const lines = header("shell-draft-preview");

    expect(lines).toEqual(
      expect.arrayContaining(["configuration_fingerprint = null", ...COMMENTS.draftPreview]),
    );
    expect(lines.filter((line) => /publish/i.test(line))).toEqual(
      COMMENTS.draftPreview.filter((line) => /publish/i.test(line)),
    );
  });

  it("says how the file is used, and what each shape of value is", () => {
    for (const branch of SHELL_BRANCH_NAMES) {
      expect(header(branch)).toEqual(
        expect.arrayContaining([...SHELL_COMMENTS.legend, ...SHELL_COMMENTS.usage]),
      );
    }
  });
});

describe("a request preview", () => {
  it("shows the method, the URL, the headers and the body of one call", () => {
    const preview = rendered("shell-calculated-cost").find(
      (file) => file.path === "request_previews/ubb_record_chat_completion.http",
    )!;
    const lines = preview.contents.split("\n").filter((line) => !line.startsWith("#"));

    expect(lines.slice(0, 5)).toEqual([
      "",
      "POST $UBB_BASE_URL/api/v1/metering/usage",
      "Authorization: Bearer $UBB_API_KEY",
      "Content-Type: application/json",
      "",
    ]);
    expect(lines.slice(5).join("\n")).toBe(
      [
        "{",
        '  "customer_id": $customer_id,',
        '  "idempotency_key": $idempotency_key,',
        '  "task_id": $task_id,',
        '  "event_type": "chat.completion",',
        '  "provider": "google",',
        '  "measurements": {',
        '    "input_tokens": $response["usageMetadata"]["promptTokenCount"],',
        '    "output_tokens": $response["usageMetadata"]["candidatesTokenCount"],',
        '    "searches": $searches',
        "  }",
        "}",
        "",
      ].join("\n"),
    );
  });

  it("writes a place in the route from the value that fills it, and no address", () => {
    const close = rendered("shell-calculated-cost").find(
      (file) => file.path === "request_previews/ubb_close_task.http",
    )!;

    expect(close.contents).toContain("POST $UBB_BASE_URL/api/v1/tasks/$task_id/close\n");
    // The value that fills the route is not also a key of the body.
    expect(close.contents).not.toContain('"task_id"');
  });

  it("carries no readiness verdict, and the header of the runnable file does", () => {
    for (const branch of SHELL_BRANCH_NAMES) {
      const blueprint = BRANCHES[branch]!();
      const previews = of(branch, "request_preview");
      const verdicts = Object.values(SHELL_READINESS_COMMENTS).flat();

      expect(previews.length).toBeGreaterThan(2);
      for (const preview of previews) {
        expect(preview.contents, preview.path).not.toMatch(/readiness/i);
        expect(preview.contents, preview.path).not.toMatch(/diagnostic|scaffold|blocked|complete/i);
        for (const line of verdicts) expect(preview.contents).not.toContain(line);
        // What it does say of itself is that it is not the runnable file.
        expect(hashComments(preview.contents).map(commentText)).toEqual(
          expect.arrayContaining([...SHELL_COMMENTS.preview]),
        );
      }
      expect(moduleOf(branch).contents).toContain(`# readiness = "${blueprint.readiness}"`);
      for (const line of SHELL_READINESS_COMMENTS[blueprint.readiness]) {
        expect(moduleOf(branch).contents).toContain(`# ${line}`);
      }
    }
  });

  it("is not the runnable file: it defines nothing and runs nothing", () => {
    for (const preview of of("shell-explicit-subtasks", "request_preview")) {
      expect(preview.path).toMatch(/^request_previews\/ubb_[a-z_]+\.http$/);
      expect(preview.contents).not.toMatch(/\bcurl\b|\bjq\b|\(\) \{/);
    }
  });
});

describe("the shapes a value takes in a shell file", () => {
  it("writes a kind of work sold whole with what delivering it does", () => {
    const fixed = hashComments(moduleOf("shell-fixed-price").contents).map(commentText);
    const perEvent = hashComments(moduleOf("shell-direct-task-events").contents).map(commentText);

    expect(fixed).toEqual(expect.arrayContaining([...PRICING_MODE_COMMENTS.fixed!]));
    expect(perEvent).not.toEqual(expect.arrayContaining([...PRICING_MODE_COMMENTS.fixed!]));
  });

  it("writes an unconfigured literal as a call that raises, naming the token", () => {
    const defined = functionsOf(moduleOf("shell-scaffold").contents);
    const body = defined.find((each) => each.name === "_ubb_jq_body_start_task")!;
    const start = defined.find((each) => each.name === "ubb_start_task")!;

    expect(body.lines).toContain('    "task_type": not_configured("task_type")');
    // And the call refuses before it gets there.
    expect(start.lines.slice(1, 4).join("\n")).toContain(
      `return "$${SHELL_EXIT.notConfigured.name}"`,
    );
  });

  it("never writes a placeholder where a value is missing", () => {
    for (const branch of ["shell-scaffold", "shell-blocked", "shell-unreadable-shape"]) {
      for (const file of rendered(branch)) {
        expect(file.contents, file.path).not.toMatch(/__[A-Z_]+__|TODO|REPLACE|YOUR_|<[a-z_ ]+>/);
      }
    }
  });

  it("reads a declared path off the supplier's JSON, segment by segment as declared", () => {
    const module = moduleOf("shell-explicit-subtasks").contents;

    expect(module).toContain(
      '      "prompt_tokens": ($p_response[0] | read(["usageMetadata","promptTokenCount"]))',
    );
    // A path spelled against its shape's convention is emitted as declared.
    expect(module).toContain(
      '      "candidate_tokens": ($p_response[0] | read(["usage_metadata","candidates_token_count"])),',
    );
  });

  it("guesses no way to read a response it is not declared to be able to read", () => {
    const module = moduleOf("shell-unreadable-shape").contents;

    expect(module).toContain('"input_tokens": not_configured("measurements.input_tokens"),');
    expect(module).not.toMatch(/\| read\(/);
    expect(module).not.toContain("--slurpfile");
    // The parameter is still the call's: its shape is the declared one.
    const record = functionsOf(module).find((each) => each.name === "ubb_record_chat_completion")!;
    expect(parametersOf(record)).toContain("response");
  });

  it("asks a record block whose work the event belongs to, and a Subtask block for none", () => {
    const block = (path: string) =>
      rendered("shell-explicit-subtasks").find((file) => file.path === path)!.contents;

    // An event may belong to the Task or to a Subtask, so its block reads the
    // id off nothing. A Subtask's parent is the work it sits inside.
    expect(block("call_sites/ubb_record_gemini_generate.sh")).toContain(
      '  task_id="$task_id" \\\n',
    );
    expect(block("call_sites/ubb_start_subtask_summarise.sh")).toContain(
      '  parent_task_id="$task_id" \\\n',
    );
  });

  it("emits the reserved status through its one constant, and the literal once", () => {
    for (const branch of SHELL_BRANCH_NAMES) {
      const code = shellCode(moduleOf(branch).contents);
      const twenty = code.filter((line) => /(^|[^0-9A-Za-z_])20([^0-9]|$)/.test(line));

      expect(twenty).toEqual([`${SHELL.stopExitStatusName}=${SHELL.stopExitStatus}`]);
      expect(code.filter((line) => line.includes(`return "$${SHELL.stopExitStatusName}"`)).length)
        .toBeGreaterThanOrEqual(2);
    }
  });
});

describe("what the shell renderer refuses", () => {
  function changed(
    change: (blueprint: ResolvedIntegrationBlueprint) => void,
  ): ResolvedIntegrationBlueprint {
    const blueprint = fixture("shell-calculated-cost");
    change(blueprint);
    return blueprint;
  }

  // Each case names the refusal it expects by its message, so a document
  // refused for some other reason does not pass for this one.
  const REFUSED: [string, RegExp, (blueprint: ResolvedIntegrationBlueprint) => void][] = [
    [
      "an operation it has no call for",
      /no call for the operation api_v1_something_else/,
      (b) => {
        b.calls[1]!.operation_id = "api_v1_something_else";
      },
    ],
    [
      "a parameter a shell function cannot take",
      /parameter name "not an identifier" is not one a shell function can take/,
      (b) => {
        b.calls[0]!.arguments[1]!.parameter_name = "not an identifier";
      },
    ],
    [
      "a Blueprint with no close of the work",
      /one close of the work, and this one has 0/,
      (b) => {
        b.calls.pop();
      },
    ],
    [
      "a Blueprint with two closes",
      /one close of the work, and this one has 2/,
      (b) => {
        b.calls.push(structuredClone(b.calls.at(-1)!));
      },
    ],
    [
      "a route with a place no token fills",
      /has a place for task_id, and no token fills it/,
      (b) => {
        const close = b.calls.at(-1)!;
        close.arguments = close.arguments.filter((argument) => argument.name !== "task_id");
      },
    ],
    [
      "a record that names no key its event is sent under",
      /names no idempotency_key parameter/,
      (b) => {
        const record = b.calls[1]!;
        record.arguments = record.arguments.filter(
          (argument) => argument.name !== "idempotency_key",
        );
      },
    ],
    [
      "one parameter asked for as two kinds of value",
      /the parameter searches of api_v1_metering_endpoints_record_usage is asked for as two kinds of value: text and number/,
      (b) => {
        for (const argument of b.calls[1]!.arguments) {
          if (argument.name === "customer_id") argument.parameter_name = "searches";
        }
      },
    ],
    [
      "a path that is not a list of segments",
      /source path is not a list of segments/,
      (b) => {
        for (const argument of everyArgument(b)) {
          if (argument.name.endsWith(".source_path")) argument.value = "usage.input_tokens";
        }
      },
    ],
    [
      "an amount representation it has no conversion for",
      /furlongs is not an amount representation this target converts/,
      (b) => {
        const reported = fixture("shell-reported-cost");
        for (const argument of everyArgument(reported)) {
          if (argument.name.endsWith(".amount_representation")) argument.value = "furlongs";
        }
        b.calls = reported.calls;
      },
    ],
    [
      "two credentials where a file has one",
      /name different credentials/,
      (b) => {
        b.calls[0]!.arguments[0]!.environment_variable = "SOMETHING_ELSE";
      },
    ],
  ];

  it.each(REFUSED)("refuses %s rather than writing a file that is wrong", (_what, message, change) => {
    expect(() => render(changed(change))).toThrow(BlueprintNotRenderable);
    expect(() => render(changed(change))).toThrow(message);
  });

  it("renders the Blueprint those were made from", () => {
    expect(() => render(changed(() => {}))).not.toThrow();
  });

  it("does not ask a shell Blueprint for an SDK major, and states the one it is given", () => {
    // NOT a Blueprint the routes answered: a shell document that names an
    // SDK major anyway. A shell file is written against no SDK, so there is
    // nothing to refuse — and the header says what the document says.
    const module = only(
      render(changed((b) => {
        b.sdk_major_version = 3;
      })),
      "module",
    ).contents;

    expect(module).toContain("# sdk_major_version = 3\n");
  });
});
