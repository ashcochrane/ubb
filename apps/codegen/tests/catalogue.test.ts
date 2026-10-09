/**
 * The renderer catalogue: closed, versioned, and in step with the registry
 * (#577, owner ruling of 2026-09-25 item 9).
 *
 * The catalogue's symbols are pinned HERE and are deliberately not registry
 * concepts. What it says ABOUT a registry concept — a sentence per diagnostic
 * code, a sentence per verdict — is held to the registry's own value sets, so
 * a code the registry gains cannot arrive as a diagnostic with nothing said
 * about it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import * as catalogue from "../src/catalogue.ts";
import {
  AMOUNT_REPRESENTATION,
  CATALOGUE_VERSION,
  COMMENTS,
  ENVIRONMENT,
  MESSAGES,
  MICROS_PER_MINOR_UNIT,
  PRICING_MODE_COMMENTS,
  PYTHON,
  READINESS_COMMENTS,
  REMEDIATION,
  RESPONSE_REPRESENTATION,
  SHELL,
  SHELL_COMMENTS,
  SHELL_EXIT,
  SHELL_FILE,
  SHELL_MESSAGES,
  SHELL_READINESS_COMMENTS,
} from "../src/index.ts";
import { STOP_FIELDS } from "../src/lifecycle.ts";
import { FIXTURE_NAMES, fixture, FIXTURES, PACKAGE_ROOT, REPO_ROOT } from "./support/fixtures.ts";
import { registry } from "./support/python.ts";

const REGISTRY = registry(
  "diagnostic_code",
  "integration_readiness",
  "amount_representation",
  "pricing_mode",
  "response_shape_representation",
  "stop_behavior",
  "task_outcome",
  "outcome_reason",
);

describe("the catalogue's symbols", () => {
  it("are the ones ruled, spelled as ruled", () => {
    expect(ENVIRONMENT).toEqual({ apiKey: "UBB_API_KEY", baseUrl: "UBB_BASE_URL" });
    expect(SHELL).toEqual({
      stopMetadata: "stop_requested",
      stopExitStatusName: "UBB_EXIT_STOP_REQUESTED",
      stopExitStatus: 20,
    });
  });

  it("keep the stop's status clear of every other status a shell file returns", () => {
    const others = Object.values(SHELL_EXIT);

    expect(others.length).toBeGreaterThanOrEqual(5);
    // Each through a named constant of its own, and no two the same.
    expect(new Set(others.map((exit) => exit.status)).size).toBe(others.length);
    expect(new Set(others.map((exit) => exit.name)).size).toBe(others.length);
    for (const exit of others) {
      expect(exit.name, exit.name).toMatch(/^UBB_EXIT_[A-Z_]+$/);
      expect(exit.name).not.toBe(SHELL.stopExitStatusName);
      // The `sysexits.h` block, which is what 20 was chosen to stand clear of.
      expect(exit.status, exit.name).toBeGreaterThanOrEqual(64);
      expect(exit.status, exit.name).toBeLessThanOrEqual(78);
    }
    // And the stop's own is none of the statuses a shell gives a meaning to:
    // success, plain failure, misuse, not runnable, not found, a signal.
    expect(SHELL.stopExitStatus).toBe(20);
    expect([0, 1, 2, 126, 127]).not.toContain(SHELL.stopExitStatus);
    expect(SHELL.stopExitStatus).toBeLessThan(64);
  });

  it("name what a shell file is made of, and nothing a tenant's shell already has", () => {
    for (const name of [SHELL_FILE.taskId, SHELL_FILE.response, SHELL_FILE.stopRequested]) {
      expect(name).toMatch(/^UBB_[A-Z_]+$/);
    }
    for (const name of [
      SHELL_FILE.startTask, SHELL_FILE.runTask, SHELL_FILE.closeTask,
      SHELL_FILE.startSubtaskPrefix, SHELL_FILE.recordPrefix,
    ]) {
      expect(name).toMatch(/^ubb_[a-z_]+$/);
    }
    // The stop's metadata is held under the name ruled for it.
    expect(SHELL_FILE.stopRequested).toBe(`UBB_${SHELL.stopMetadata.toUpperCase()}`);
    expect(SHELL_FILE.heredoc).toMatch(/^[A-Z_]+$/);
  });

  it("name the three fixed functions for the Task, the domain's own noun, and no other", () => {
    // Owner ruling on PR #598: the outer runner is `ubb_run_task`. The phrase
    // the Python target's wrapper is named for is explanation, and is not a
    // second public noun in the shell file's API.
    expect([SHELL_FILE.startTask, SHELL_FILE.runTask, SHELL_FILE.closeTask]).toEqual([
      "ubb_start_task", "ubb_run_task", "ubb_close_task",
    ]);
    const shell = JSON.stringify([SHELL_FILE, SHELL_COMMENTS, SHELL_MESSAGES]);
    expect(shell).not.toMatch(/unit_of_work/);
  });

  it("hold the largest amount a money column takes, to the digit", () => {
    expect(SHELL_FILE.microsLimit).toBe((2n ** 63n - 1n).toString());
    // A whole number of this many digits is exact in a double, which is what
    // the oldest jq a file may meet holds a number in.
    expect(Number.isSafeInteger(Number("9".repeat(SHELL_FILE.exactDigits)))).toBe(true);
    expect(Number.isSafeInteger(Number("9".repeat(SHELL_FILE.exactDigits + 1)))).toBe(false);
  });

  it("hold no host: where the API is, is not the renderer's to say", () => {
    // Owner ruling on PR #597: the renderer keeps no second copy of the
    // platform's service location. Nothing in the catalogue is an address.
    expect(JSON.stringify(catalogue)).not.toMatch(/https?:\/\/|localhost/);
  });

  it("name the credential the server withholds under the same variable", () => {
    for (const name of FIXTURE_NAMES) {
      const variables = fixture(name)
        .calls.flatMap((call) => call.arguments)
        .filter((argument) => argument.binding_class === "secret_reference")
        .map((argument) => argument.environment_variable);

      expect(variables.length, name).toBeGreaterThan(0);
      expect(new Set(variables), name).toEqual(new Set([ENVIRONMENT.apiKey]));
    }
  });

  it("name the SDK major this tree ships, and the one a Blueprint names", () => {
    expect(Number(REGISTRY.sdk_version.split(".")[0])).toBe(PYTHON.sdkMajorVersion);
    expect(fixture("calculated-cost").sdk_major_version).toBe(PYTHON.sdkMajorVersion);
  });

  it("spell the two stop behaviours as the registry does", () => {
    expect([PYTHON.stopBehaviorRaise, PYTHON.stopBehaviorReturn].sort()).toEqual(
      REGISTRY.values.stop_behavior,
    );
  });

  it("names every outcome a close may declare as the registry does, and holds none to declare itself", () => {
    expect(REGISTRY.values.task_outcome!.length).toBeGreaterThan(2);
    // The sentence above a close names every outcome there is.
    const sentence = SHELL_COMMENTS.close.join(" ");
    for (const outcome of REGISTRY.values.task_outcome!) expect(sentence).toContain(outcome);
    // Owner ruling on PR #598: a shell file never writes an outcome of its
    // own, so the catalogue holds no outcome and no reason as a value.
    const values = Object.values(SHELL_FILE).map(String);
    for (const word of [...REGISTRY.values.task_outcome!, ...REGISTRY.values.outcome_reason!]) {
      expect(values, word).not.toContain(word);
    }
  });
});

describe("what the catalogue says about a registry concept", () => {
  it("has remediation for every diagnostic code, and for no other", () => {
    expect(REGISTRY.values.diagnostic_code!.length).toBeGreaterThan(10);
    expect(Object.keys(REMEDIATION).sort()).toEqual(REGISTRY.values.diagnostic_code);
  });

  it("says a valid constant waits only on this version, never that its value is missing", () => {
    // #571: a constant is declared with its value, so the declaration is
    // complete and only the Code Builder lacks something. Nothing may read as
    // a fault in the declaration, or as constants not being supported.
    const words = REMEDIATION.constant_measurement_not_renderable.join(" ");

    expect(words).toContain("valid platform configuration");
    expect(words).toContain("This Code Builder version cannot yet generate code that uses");
    expect(words).toContain("Nothing in the declaration needs to change.");
    expect(words).not.toMatch(/missing|not declared|unsupported|request below/i);
  });

  it("tells a cost read off the response what to read, where a caller is told what to pass", () => {
    // #583: the float refusal of a cost read off the supplier's response is
    // about the response, so it says what to READ — never "pass", which is a
    // caller's word for a value the caller holds.
    expect(MESSAGES.floatRead).toContain("read the response's integer or its decimal string instead");
    expect(MESSAGES.floatRead).not.toMatch(/\bpass\b/);
    expect(MESSAGES.float).toMatch(/\bpass\b/);
  });

  it("leaves a currency UBB holds and the tenant does not to UBB, on both targets", () => {
    // #583 D1: a currency read off the response is refused here only where it
    // is no code UBB holds. One it holds that is not the tenant's is refused
    // by the one shared rule when the event is recorded: no file carries the
    // tenant's currency to compare, and none says it does.
    for (const lines of [COMMENTS.responseCurrency, SHELL_COMMENTS.responseCurrency]) {
      const words = lines.join(" ");
      expect(words).toContain("that UBB does not hold is refused");
      expect(words).toContain("refused by UBB when the event is recorded");
      expect(words).not.toMatch(/compare|matches your|tenant's currency/i);
    }
  });

  it("agrees with the committed contract about which codes there are", () => {
    const known = JSON.parse(
      readFileSync(join(REPO_ROOT, "openapi", "known-values.json"), "utf-8"),
    ) as { concepts: Record<string, { values: string[] }> };

    expect(Object.keys(REMEDIATION).sort()).toEqual(
      [...known.concepts.diagnostic_code!.values].sort(),
    );
  });

  it("says what every verdict means, and no other", () => {
    expect(Object.keys(READINESS_COMMENTS).sort()).toEqual(
      REGISTRY.values.integration_readiness,
    );
  });

  it("says what every verdict means for a shell file too, in that file's own words", () => {
    expect(Object.keys(SHELL_READINESS_COMMENTS).sort()).toEqual(
      REGISTRY.values.integration_readiness,
    );
    // Neither target's sentences name what only the other one has.
    const shell = Object.values(SHELL_READINESS_COMMENTS).flat().join(" ");
    const python = Object.values(READINESS_COMMENTS).flat().join(" ");
    expect(shell).not.toContain(PYTHON.notReadyError);
    expect(shell).toContain(SHELL_EXIT.notConfigured.name);
    expect(python).not.toContain(SHELL_EXIT.notConfigured.name);
  });

  it("converts by moving the point: every currency's multiplier is a power of ten", () => {
    // What lets a shell file convert on digits alone, with no arithmetic on
    // the amount. A currency that broke it is refused at render.
    for (const [currency, micros] of Object.entries(MICROS_PER_MINOR_UNIT)) {
      expect(String(micros), currency).toMatch(/^10*$/);
    }
  });

  it("converts every amount representation, and no other", () => {
    expect(Object.values(AMOUNT_REPRESENTATION).sort()).toEqual(
      REGISTRY.values.amount_representation,
    );
  });

  it("says what delivering means under every pricing mode, and no other", () => {
    expect(Object.keys(PRICING_MODE_COMMENTS).sort()).toEqual(REGISTRY.values.pricing_mode);
  });

  it("reads every response shape representation, and no other", () => {
    expect(Object.values(RESPONSE_REPRESENTATION).sort()).toEqual(
      REGISTRY.values.response_shape_representation,
    );
  });

  it("holds the platform's own currency table", () => {
    const platform = JSON.parse(
      readFileSync(join(FIXTURES, "micros-per-minor-unit.json"), "utf-8"),
    ) as Record<string, number>;

    expect(Object.keys(platform).length).toBeGreaterThan(5);
    expect(MICROS_PER_MINOR_UNIT).toEqual(platform);
  });
});

describe("the catalogue's text", () => {
  const groups = {
    COMMENTS, READINESS_COMMENTS, REMEDIATION, PRICING_MODE_COMMENTS,
    SHELL_COMMENTS, SHELL_READINESS_COMMENTS,
  };
  const lines = Object.values(groups).flatMap((group) => Object.values(group).flat());

  it("is lines a comment can hold: short, plain, and trimmed", () => {
    expect(lines.length).toBeGreaterThan(170);
    for (const line of lines) {
      expect(line.length, line).toBeLessThanOrEqual(76);
      expect(line, line).toMatch(/^[\x20-\x7e]+$/);
      expect(line.trimEnd(), line).toBe(line);
      // A comment inside a jq program is continued by a backslash at its
      // end, on some versions of jq: no line holds one anywhere.
      expect(line, line).not.toContain("\\");
    }
  });

  it("is messages a Python string, an f-string and a jq string can hold as they stand", () => {
    const messages = [...Object.values(MESSAGES), ...Object.values(SHELL_MESSAGES)];

    expect(messages.length).toBeGreaterThan(40);
    for (const message of messages) {
      expect(message, message).toMatch(/^[\x20-\x7e]+$/);
      expect(message, message).not.toMatch(/["{}\\]/);
    }
    // An apostrophe is allowed, and one message has one: in a shell file a
    // message is a quoted word, which the renderer escapes it into.
    expect(messages.filter((message) => message.includes("'"))).not.toEqual([]);
  });

  // The Python boundary hands the log the key and then `STOP_FIELDS`, in
  // order (ADR-0016 §4): the sentence must name the same fields in the same
  // order, or a figure would be logged under another field's name.
  it("names each field of the stop in the Python log as the boundary passes them (#585)", () => {
    const named = [...MESSAGES.stop.matchAll(/(\w+)=%r/g)].map((match) => match[1]);
    expect(named).toEqual([...STOP_FIELDS]);
    expect(MESSAGES.stop.split("%r")).toHaveLength(STOP_FIELDS.length + 2);
  });

  it("names its own version in the line that says what generated a file", () => {
    expect(COMMENTS.generated[0]).toContain(`renderer catalogue version ${CATALOGUE_VERSION}`);
  });

  it("is pinned, whole, to its version", async () => {
    // Every exported member, as it stands. A member added, removed or
    // reworded fails here until the file is re-taken. Re-taking it is one
    // command, so what this buys is not a refusal: it is that a change under
    // an unchanged number shows up as a diff of a file named for the version,
    // and a new number as a new file.
    const whole = Object.fromEntries(
      Object.entries(catalogue).sort(([left], [right]) => left.localeCompare(right)),
    );

    await expect(`${JSON.stringify(whole, null, 2)}\n`).toMatchFileSnapshot(
      join(PACKAGE_ROOT, "tests", "__snapshots__", `catalogue.v${CATALOGUE_VERSION}.json`),
    );
  });
});
