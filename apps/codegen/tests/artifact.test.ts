/**
 * What a rendered artifact is, read off the text `render` returns (#577).
 *
 * The files, the header, the two classes of comment, the three shapes a value
 * takes and the state of one of them, and the rule that the lines a tenant
 * maintains carry no generated value. Python's own parser answers what is a
 * comment, what is a literal and what a function requires — never a pattern
 * matched against source text.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  BlueprintNotRenderable,
  COMMENTS,
  ENVIRONMENT,
  PRICING_MODE_COMMENTS,
  READINESS_COMMENTS,
  REMEDIATION,
  render,
} from "../src/index.ts";
import type { ResolvedIntegrationBlueprint } from "../src/blueprint.ts";
import {
  everyArgument,
  fixture,
  FIXTURES,
  PACKAGE_ROOT,
} from "./support/fixtures.ts";
import { compiled } from "./support/python.ts";
import {
  BRANCH_NAMES,
  BRANCHES,
  commentText,
  factsOf,
  hashComments,
  moduleOf,
  only,
  PLANTED,
  provenanceOf,
  PYTHON_BRANCH_NAMES,
  rendered,
} from "./support/rendered.ts";

const CATALOGUE_LINES = new Set<string>(
  [COMMENTS, READINESS_COMMENTS, REMEDIATION, PRICING_MODE_COMMENTS].flatMap((group) =>
    Object.values(group).flat(),
  ),
);

/** Every comment of every file of a branch, as its text. */
function comments(branch: string): string[] {
  const found = Object.values(factsOf(branch)).flatMap((file) => file.comments);
  const environment = only(rendered(branch), "environment_example");
  return [...found, ...hashComments(environment.contents)].map(commentText);
}

describe.each(PYTHON_BRANCH_NAMES)("the %s artifact", (branch) => {
  it("is one module, its call-site blocks, an environment example and a verify script", () => {
    const files = rendered(branch);
    const kinds = files.map((file) => file.kind);

    expect(kinds.filter((kind) => kind === "module")).toHaveLength(1);
    expect(kinds.filter((kind) => kind === "environment_example")).toHaveLength(1);
    expect(kinds.filter((kind) => kind === "verify_script")).toHaveLength(1);
    expect(kinds.filter((kind) => kind === "call_site").length).toBeGreaterThan(0);
    expect(new Set(files.map((file) => file.path)).size).toBe(files.length);
    expect(only(files, "module").path).toBe("ubb_integration.py");
    expect(only(files, "environment_example").path).toBe(".env.example");
  });

  it("compiles, every Python file of it", () => {
    const answers = compiled(rendered(branch));

    expect(Object.keys(answers).length).toBeGreaterThan(2);
    expect(Object.values(answers).filter((refusal) => refusal !== null)).toEqual([]);
  });

  it("carries only comments that are provenance or a catalogue member", () => {
    const found = comments(branch);
    const neither = found.filter(
      (text) => !CATALOGUE_LINES.has(text) && provenanceOf(text) === null,
    );

    expect(found.length).toBeGreaterThan(10);
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

    expect(stated.length).toBeGreaterThan(5);
    expect(stated.filter((statement) => !carried.has(statement))).toEqual([]);
  });

  it("has no docstring, which would be a third class of prose", () => {
    for (const file of Object.values(factsOf(branch))) {
      expect(file.has_module_docstring).toBe(false);
      for (const facts of Object.values(file.functions)) {
        expect(facts.has_docstring).toBe(false);
      }
    }
  });

  it("puts no generated value in a call-site block", () => {
    const blocks = Object.entries(factsOf(branch)).filter(([path]) =>
      path.startsWith("call_sites/"),
    );

    expect(blocks.length).toBeGreaterThan(0);
    for (const [path, facts] of blocks) {
      // Not one string, number or bytes literal — `...`, where the tenant's
      // own code goes, is the only constant a block holds. So there is no
      // value in a block for a change of configuration to make stale.
      expect(facts.constants, path).toEqual([]);
    }
  });

  it("names nothing in a call-site block but exports, parameters and the handles", () => {
    const blueprint = BRANCHES[branch]!();
    const module = factsOf(branch)["ubb_integration.py"]!;
    const allowed = new Set([
      ...Object.keys(module.functions),
      ...everyArgument(blueprint).flatMap((argument) =>
        argument.parameter_name ? [argument.parameter_name] : [],
      ),
      "recorded_at",
      "task",
      "subtask",
      "stop",
      "acknowledgement",
      "outcome_reason",
      "UBBStopRequested",
    ]);

    for (const [path, facts] of Object.entries(factsOf(branch))) {
      if (!path.startsWith("call_sites/")) continue;
      expect(facts.names.filter((name) => !allowed.has(name)), path).toEqual([]);
    }
  });

  it("writes every platform-known argument as the literal Python reads back unchanged", () => {
    const blueprint = BRANCHES[branch]!();
    const module = factsOf(branch)["ubb_integration.py"]!;
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
    expect(sent.length).toBeGreaterThanOrEqual(branch === "scaffold" ? 0 : 1);

    for (const argument of sent) {
      expect(module.strings, argument.name).toContain(argument.value);
    }
  });

  it("states every platform-known token in the function for its call", () => {
    const blueprint = BRANCHES[branch]!();
    // Below the header only, and only indented comments: the header's own
    // list of declarations must not be what satisfies this.
    const lines = moduleOf(branch).contents.split("\n");
    const stated = lines
      .slice(lines.findIndex((line) => line.startsWith("from ")))
      .filter((line) => /^ {8,}# /.test(line))
      .map((line) => line.trim())
      .filter((line) => line.startsWith("# "))
      .map((line) => provenanceOf(commentText(line)))
      .filter((statement) => statement !== null);

    for (const call of blueprint.calls) {
      for (const argument of call.arguments) {
        if (argument.binding_class !== "platform_known" || !argument.configured) continue;
        const matching = stated.filter(
          (statement) =>
            statement.name === argument.name &&
            JSON.stringify(statement.value) === JSON.stringify(argument.value),
        );
        expect(matching.length, argument.name).toBeGreaterThan(0);
      }
    }
  });

  it("asks for every runtime value as a required parameter, at the call it is declared for", () => {
    const blueprint = BRANCHES[branch]!();
    const module = factsOf(branch)["ubb_integration.py"]!;
    const signatures = Object.values(module.functions).map((facts) =>
      [...facts.required_keywords].sort().join(","),
    );

    for (const call of blueprint.calls) {
      if (call.operation_id.endsWith("close_task")) continue;
      const asked = [
        ...new Set(
          call.arguments.flatMap((argument) =>
            argument.binding_class === "runtime_bound" ? [argument.parameter_name!] : [],
          ),
        ),
      ].sort();
      expect(signatures, call.operation_id).toContain(asked.join(","));
    }
    for (const facts of Object.values(module.functions)) {
      // No parameter of a generated function is optional: a value left out
      // is a TypeError that names it.
      expect(facts.optional_keywords).toEqual([]);
    }
    for (const [name, facts] of Object.entries(module.functions)) {
      // And none a call site passes is positional, so none can be passed in
      // the place of another.
      if (!name.startsWith("_")) expect(facts.positional, name).toEqual([]);
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

  it("reads the credential from the environment and writes it nowhere", () => {
    const module = moduleOf(branch).contents;

    expect(module).toContain(`os.environ["${ENVIRONMENT.apiKey}"]`);
    for (const file of rendered(branch)) {
      expect(file.contents).not.toContain(PLANTED);
    }
  });
});

describe("the header", () => {
  function header(branch: string): string[] {
    const lines = moduleOf(branch).contents.split("\n");
    return lines.slice(0, lines.findIndex((line) => line.startsWith("from "))).map(commentText);
  }

  it("states the three versions, the target, the fingerprint and the verdict", () => {
    const blueprint = fixture("calculated-cost");

    expect(header("calculated-cost")).toEqual(
      expect.arrayContaining([
        "schema_version = 1",
        "renderer_contract_version = 1",
        "sdk_major_version = 3",
        'target = "python_sdk"',
        `configuration_fingerprint = "${blueprint.configuration_fingerprint}"`,
        'readiness = "complete"',
        ...READINESS_COMMENTS.complete,
      ]),
    );
  });

  it("states each Event Type's revision and the date it was published", () => {
    expect(header("direct-task-events")).toEqual(
      expect.arrayContaining([
        'event_type = "reply.sent" · published_revision 1 · published_at "2026-09-01T12:00:00+00:00"',
        'event_type = "search.run" · published_revision 1 · published_at "2026-09-01T12:00:00+00:00"',
        'task_type = "support_reply"',
      ]),
    );
  });

  it.each(["scaffold", "blocked"] as const)(
    "states a %s verdict and what it means",
    (readiness) => {
      expect(header(readiness)).toEqual(
        expect.arrayContaining([
          `readiness = "${readiness}"`,
          ...READINESS_COMMENTS[readiness],
        ]),
      );
    },
  );

  it("lists every diagnostic with its remediation and the request that fixes it", () => {
    const blueprint = fixture("blocked");
    const lines = header("blocked");

    expect(blueprint.diagnostics.length).toBeGreaterThan(3);
    for (const diagnostic of blueprint.diagnostics) {
      const at = lines.indexOf(
        `diagnostic = "${diagnostic.code}" · severity "${diagnostic.severity}"` +
          ` · ${diagnostic.object_kind} ${JSON.stringify(diagnostic.key)}` +
          ` · field ${JSON.stringify(diagnostic.field)}`,
      );
      expect(at, diagnostic.code).toBeGreaterThan(-1);
      const after = lines.slice(at + 1, at + 1 + REMEDIATION[diagnostic.code].length);
      expect(after).toEqual(REMEDIATION[diagnostic.code]);
      // A diagnostic with nothing to change carries no request (#571), and
      // the header then states none rather than a null.
      const request = diagnostic.remediation_request ?? null;
      const stated = `remediation_request = ${JSON.stringify(request)}`;
      if (request === null) expect(lines).not.toContain(stated);
      else expect(lines).toContain(stated);
    }
    expect(blueprint.diagnostics.filter((d) => d.remediation_request == null).map((d) => d.code)).toEqual([
      "constant_measurement_not_renderable",
    ]);
  });

  it("lists a diagnostic that names no declaration, and offers no request for it", () => {
    const lines = header("scaffold");

    expect(lines).toContain(
      'diagnostic = "task_type_not_selected" · severity "blocking" · task_type null · field null',
    );
    expect(lines.filter((line) => line.startsWith("remediation_request"))).toEqual([]);
  });

  it("lists an advisory and still says complete", () => {
    const lines = header("explicit-subtasks");

    expect(lines).toContain('readiness = "complete"');
    expect(
      lines.some((line) =>
        line.startsWith('diagnostic = "source_path_convention_mismatch" · severity "advisory"'),
      ),
    ).toBe(true);
  });

  it("says a draft preview is one, and claims no fingerprint and no publication", () => {
    const lines = header("draft-preview");

    expect(lines).toEqual(
      expect.arrayContaining(["configuration_fingerprint = null", ...COMMENTS.draftPreview]),
    );
    expect(lines).toContain('event_type = "chat.completion"');
    // Nothing in a preview's header says anything was published.
    expect(lines.filter((line) => /publish/i.test(line))).toEqual(
      COMMENTS.draftPreview.filter((line) => /publish/i.test(line)),
    );
    // And a published one is not labelled a preview.
    expect(header("calculated-cost")).not.toEqual(
      expect.arrayContaining([...COMMENTS.draftPreview]),
    );
  });

  it("states the fingerprint it was given and never one of its own", () => {
    const blueprint = fixture("calculated-cost");
    blueprint.configuration_fingerprint = `sha256:${"0".repeat(64)}`;

    const module = only(render(blueprint), "module").contents;

    expect(module).toContain(`# configuration_fingerprint = "sha256:${"0".repeat(64)}"`);
    expect(module).not.toContain(fixture("calculated-cost").configuration_fingerprint);
  });

  it("is the same whatever a diagnostic's request is, but for the line that states it", () => {
    const blueprint = fixture("blocked");
    blueprint.diagnostics.find((d) => d.remediation_request != null)!.remediation_request!.route =
      "/api/v1/somewhere-else";

    const changed = only(render(blueprint), "module").contents.split("\n");
    const original = moduleOf("blocked").contents.split("\n");

    expect(changed.filter((line, index) => line !== original[index])).toHaveLength(1);
  });
});

describe("the shapes a value takes", () => {
  it("writes a kind of work sold whole with what delivering it does", () => {
    const fixed = hashComments(moduleOf("fixed-price").contents).map(commentText);
    const perEvent = hashComments(moduleOf("direct-task-events").contents).map(commentText);

    expect(fixed).toEqual(expect.arrayContaining([...PRICING_MODE_COMMENTS.fixed!]));
    expect(perEvent).toEqual(expect.arrayContaining([...PRICING_MODE_COMMENTS.event_priced!]));
    expect(perEvent).not.toEqual(expect.arrayContaining([...PRICING_MODE_COMMENTS.fixed!]));
  });

  it("writes an unconfigured literal as a call that raises, naming the token", () => {
    const module = factsOf("scaffold")["ubb_integration.py"]!;
    const start = module.functions.start_task!;
    const call = start.calls.find((made) => made.callee.endsWith(".start_task"))!;

    expect(call.keywords.task_type).toEqual({
      expression: "_not_configured('task_type')",
    });
  });

  it("never writes a placeholder where a value is missing", () => {
    for (const branch of ["scaffold", "blocked"]) {
      for (const file of rendered(branch)) {
        expect(file.contents).not.toMatch(/__[A-Z_]+__|TODO|REPLACE|YOUR_|<[a-z_ ]+>/);
      }
    }
  });

  it("reads a path off a Python object by attribute and off JSON by subscript", () => {
    expect(moduleOf("calculated-cost").contents).toContain(
      '"input_tokens": response.usage.input_tokens,',
    );
    expect(moduleOf("explicit-subtasks").contents).toContain(
      '"prompt_tokens": response["usageMetadata"]["promptTokenCount"],',
    );
    // A path spelled against its shape's convention is emitted as declared.
    expect(moduleOf("explicit-subtasks").contents).toContain(
      '"candidate_tokens": response["usage_metadata"]["candidates_token_count"],',
    );
  });

  it("reaches a key Python cannot spell as an attribute without renaming it", () => {
    const blueprint = fixture("calculated-cost");
    for (const argument of everyArgument(blueprint)) {
      if (argument.name === "measurements.input_tokens.source_path") {
        argument.value = ["usage-data", "class", "input tokens"];
      }
    }

    const module = only(render(blueprint), "module").contents;

    expect(module).toContain(
      '"input_tokens": _attribute(_attribute(_attribute(response, "usage-data"), "class"), "input tokens"),',
    );
    expect(Object.values(compiled(render(blueprint))).every((refusal) => refusal === null)).toBe(
      true,
    );
  });

  it("guesses no way to read a path whose shape declares no representation", () => {
    // NOT a Blueprint the routes answered, but the shape of one: for a
    // tenant's own response shape the resolver emits no representation token
    // (and blocks the call). The calculated-cost fixture, with that token
    // taken out.
    const blueprint = fixture("calculated-cost");
    for (const call of blueprint.calls) {
      call.arguments = call.arguments.filter(
        (argument) => argument.name !== "event_type.response_shape_representation",
      );
    }

    const files = render(blueprint);
    const module = only(files, "module").contents;

    expect(module).toContain('"input_tokens": _not_configured("measurements.input_tokens"),');
    expect(module).not.toMatch(/response[.[]/);
    expect(Object.values(compiled(files)).filter((refusal) => refusal !== null)).toEqual([]);
  });

  it("asks a record block whose work the event belongs to, and guesses for neither", () => {
    const block = (path: string) =>
      rendered("explicit-subtasks").find((file) => file.path === path)!.contents;

    // An event may belong to the Task or to a Subtask, so its block reads the
    // id off no handle. A Subtask's parent is the work it sits inside.
    expect(block("call_sites/record_gemini_generate.py")).toContain("    task_id=task_id,\n");
    expect(block("call_sites/backfill_gemini_generate.py")).toContain("    task_id=task_id,\n");
    expect(block("call_sites/start_subtask_summarise.py")).toContain(
      "    parent_task_id=task.task_id,\n",
    );
  });

  it("writes no host into any file: where the API is, is read from the environment", () => {
    // Every branch of every target: no file of any artifact holds an address.
    expect(BRANCH_NAMES.length).toBeGreaterThan(PYTHON_BRANCH_NAMES.length);
    for (const branch of BRANCH_NAMES) {
      for (const file of rendered(branch)) {
        expect(file.contents, `${branch}/${file.path}`).not.toMatch(/https?:\/\//);
        expect(file.contents, `${branch}/${file.path}`).not.toMatch(/localhost|\bubb\.dev\b/);
      }
    }
    for (const branch of PYTHON_BRANCH_NAMES) {
      expect(moduleOf(branch).contents).toContain(`os.environ.get("${ENVIRONMENT.baseUrl}")`);
    }
  });
});

describe("what the renderer refuses", () => {
  function changed(
    change: (blueprint: ResolvedIntegrationBlueprint) => void,
  ): ResolvedIntegrationBlueprint {
    const blueprint = fixture("calculated-cost");
    change(blueprint);
    return blueprint;
  }

  // Each case names the refusal it expects by its message, so a document
  // refused for some other reason does not pass for this one.
  const REFUSED: [string, RegExp, (blueprint: ResolvedIntegrationBlueprint) => void][] = [
    [
      "a target it has no renderer for",
      /no renderer for the target a_target_nothing_renders/,
      (b) => {
        // Not a value the contract admits: what a renderer older than the
        // contract would be handed.
        b.target = "a_target_nothing_renders" as ResolvedIntegrationBlueprint["target"];
      },
    ],
    [
      "a document shape it does not know",
      /reads Blueprint schema 1, and was given 2/,
      (b) => {
        b.schema_version = 2;
      },
    ],
    [
      "a renderer contract it does not know",
      /written to renderer contract 1, and the Blueprint was resolved for 2/,
      (b) => {
        b.renderer_contract_version = 2;
      },
    ],
    [
      "an SDK major it is not written against",
      /written against SDK major 3, and the Blueprint names 4/,
      (b) => {
        b.sdk_major_version = 4;
      },
    ],
    [
      "an operation it has no call for",
      /no call for the operation api_v1_something_else/,
      (b) => {
        b.calls.at(-1)!.operation_id = "api_v1_something_else";
      },
    ],
    [
      "a secret with no setup instructions",
      /no setup instructions for the environment variable SOMETHING_ELSE/,
      (b) => {
        for (const call of b.calls) call.arguments[0]!.environment_variable = "SOMETHING_ELSE";
      },
    ],
    [
      "two credentials where a module has one client",
      /name different credentials/,
      (b) => {
        b.calls[0]!.arguments[0]!.environment_variable = "SOMETHING_ELSE";
      },
    ],
    [
      "a parameter Python cannot bind",
      /parameter name "not an identifier" is not one Python can bind/,
      (b) => {
        b.calls[0]!.arguments[1]!.parameter_name = "not an identifier";
      },
    ],
    [
      "a parameter that is a keyword",
      /parameter name "class" is not one Python can bind/,
      (b) => {
        b.calls[0]!.arguments[1]!.parameter_name = "class";
      },
    ],
    [
      "a token named under a field the call does not carry",
      /"elsewhere.pricing_mode" is named under a field this call does not carry/,
      (b) => {
        b.calls[0]!.arguments[4]!.name = "elsewhere.pricing_mode";
      },
    ],
    [
      "a number it cannot carry exactly",
      /too large to be carried exactly/,
      (b) => {
        b.calls[0]!.arguments[6]!.value = 2 ** 60;
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
      "a second secret on a call, which it would otherwise drop",
      /carries 2 secret references, and a call has one credential/,
      (b) => {
        b.calls[0]!.arguments[1]!.binding_class = "secret_reference";
        b.calls[0]!.arguments[1]!.environment_variable = "UBB_API_KEY";
      },
    ],
    [
      "a secret reference where the value under a key is named",
      /"measurements.searches" is a secret reference where a call's value is named/,
      (b) => {
        for (const argument of everyArgument(b)) {
          if (argument.name === "measurements.searches") {
            argument.binding_class = "secret_reference";
            argument.environment_variable = "UBB_API_KEY";
          }
        }
      },
    ],
    [
      "a declared fact that is not a platform-known value",
      /"task_type.pricing_mode" is named as a declared fact and is not a platform-known value/,
      (b) => {
        b.calls[0]!.arguments[4]!.binding_class = "runtime_bound";
        b.calls[0]!.arguments[4]!.parameter_name = "pricing_mode";
      },
    ],
  ];

  it.each(REFUSED)("refuses %s rather than writing a file that is wrong", (_what, message, change) => {
    expect(() => render(changed(change))).toThrow(BlueprintNotRenderable);
    expect(() => render(changed(change))).toThrow(message);
  });

  it("renders the Blueprint those were made from", () => {
    // The positive control: each refusal above is of the change, not of the
    // fixture the change was made to.
    expect(() => render(changed(() => {}))).not.toThrow();
  });
});

describe("no secret is held anywhere a renderer's test can see", () => {
  const SHAPED_LIKE_A_KEY = [
    /ubb_(live|test)_[A-Za-z0-9]{8,}/,
    /\bsk_(live|test)_[A-Za-z0-9]{8,}/,
    /\bwhsec_[A-Za-z0-9]{8,}/,
    /Bearer\s+[A-Za-z0-9._-]{16,}/,
  ];

  function textFilesUnder(directory: string): string[] {
    return readdirSync(directory).flatMap((entry) => {
      const path = join(directory, entry);
      if (statSync(path).isDirectory()) return textFilesUnder(path);
      return [path];
    });
  }

  it.each([FIXTURES, join(PACKAGE_ROOT, "tests"), join(PACKAGE_ROOT, "src")])(
    "nothing under %s is shaped like a key",
    (directory) => {
      const files = textFilesUnder(directory).filter((path) => !path.includes("generated"));

      expect(files.length).toBeGreaterThan(3);
      for (const path of files) {
        const text = readFileSync(path, "utf-8");
        for (const pattern of SHAPED_LIKE_A_KEY) {
          expect(pattern.test(text), `${path} ~ ${pattern}`).toBe(false);
        }
      }
    },
  );

  it("can find a key that is there", () => {
    const planted = ["ubb", "live", "abcdefgh12345678"].join("_");

    expect(SHAPED_LIKE_A_KEY.some((pattern) => pattern.test(`api_key = "${planted}"`))).toBe(true);
  });

  it("no fixture carries a value on a secret token, so none could leak one", () => {
    for (const name of readdirSync(join(FIXTURES, "blueprints"))) {
      const blueprint = JSON.parse(
        readFileSync(join(FIXTURES, "blueprints", name), "utf-8"),
      ) as ResolvedIntegrationBlueprint;
      const secrets = everyArgument(blueprint).filter(
        (argument) => argument.binding_class === "secret_reference",
      );
      expect(secrets.length, name).toBeGreaterThan(0);
      expect(secrets.filter((argument) => argument.value != null), name).toEqual([]);
    }
  });
});
