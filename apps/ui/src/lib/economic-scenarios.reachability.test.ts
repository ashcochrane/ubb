// A §9.2 fixture is not complete until a mock or a component test consumes it
// (#371, spec §22 ruling 10(b)).
//
// ⚠ THIS IS THE CHECK, NOT A REVIEWER. Slice 3 wrote five canonical cost
// scenarios and wired two of them; the other three reached nothing but
// `economic-scenarios.test.ts`, and that went unnoticed until a later window
// traced it by hand. The commit message even said all five were orphaned, which
// was wrong in the other direction — nobody could tell without reading the
// import graph, so nobody did.
//
// A fixture nothing renders cannot catch the defect the obligation exists to
// prevent. `const displayed = amount ?? 0` lives in a RENDERER; a scenario
// asserted only against itself proves the scenario is well-formed and says
// nothing about the console. And the two values that break under a naive
// zero-coalesce — `unknown` and `waived` — are the two this slice adds, so
// building them the way slice 3 did would have shipped the same silent gap six
// times over.
//
// WHAT COUNTS AS A CONSUMER, and why these two:
//
//   a feature mock       `features/*/api/mock*.ts` — the fixture reaches a
//                        payload the console is actually served, so every
//                        component test on that surface renders it
//   a component test     `*.test.tsx` — a rendering assertion, including one
//                        against a fixture the mock does not author
//
// A `.test.ts` is deliberately NOT a consumer. That is the unit-test category
// this rule exists to rule out, and admitting it would make the check pass on
// exactly the arrangement it was written to catch.
//
// ⚠ IT READS IMPORTS, NOT CALLS, AND LINT IS WHAT CLOSES THAT GAP. A consumer
// that imported a scenario and never called it would satisfy every assertion
// below — so on its own this would be one step weaker than it reads. It is not
// on its own: `@typescript-eslint/no-unused-vars` is configured as an ERROR in
// `eslint.config.js`, so an imported-and-uncalled fixture fails the lint gate
// on the same commit. Two checks, one property, and neither has to reimplement
// the other's job. Stated here because a reader who spots the gap deserves the
// answer beside it rather than a fix that duplicates a rule already enforced.
//
// ⚠ IT READS SOURCE TEXT, and that is a deliberate trade. The alternative —
// importing every mock and inspecting what it serves — cannot see a fixture
// consumed by a component test at all, and cannot see WHICH ARGUMENT a
// parameterised scenario was called with. Both matter here: the sixth state
// this slice owes is `priceNotApplicable("tenant_not_billing")`, which is one
// argument away from its sibling and lives in a test rather than a mock.
// `import.meta.glob` is Vite's own facility, so this needs no filesystem access
// and no extra dependency.

import { describe, expect, it } from "vitest";

import * as scenarios from "./economic-scenarios";
import {
  NOT_APPLICABLE_REASON_VALUES,
  PRICING_STATUS_VALUES,
  type PricingStatus,
} from "./vocabulary";

const SOURCES = import.meta.glob("/src/**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/**
 * A feature mock, or a component test. Nothing else.
 *
 * ⚠ THE `.test.ts` EXCLUSION IS LOAD-BEARING AND IT IS EASY TO WRITE WRONG.
 * `mock[^/]*\.ts$` looks like it names the mock pair and also matches
 * `mock-data.test.ts` and `mock.test.ts` — both of which exist in this console
 * (`features/billing/api/`, `features/settings/api/`). A classifier that
 * admitted them would admit the unit-test category this whole rule exists to
 * rule out, and would do it while the file above claimed otherwise. Neither of
 * those two imports the scenario module today, so the answer would have been
 * right by luck; the first fixture wired only into one would pass in silence.
 * The alternation is exact for that reason.
 */
function isConsumer(path: string): boolean {
  return (
    /\/features\/[^/]+\/api\/mock(-data)?\.ts$/.test(path) ||
    path.endsWith(".test.tsx")
  );
}

/** Every clause of every import this file takes from the scenario module. */
function importedScenarios(source: string): string[] {
  const imports = source.matchAll(
    /import\s*\{([^}]*)\}\s*from\s*["']@\/lib\/economic-scenarios["']/g,
  );
  return [...imports].flatMap((match) =>
    (match[1] ?? "")
      .split(",")
      .map((clause) => clause.trim().replace(/^type\s+/, "").split(/\s+as\s+/)[0] ?? "")
      .filter(Boolean),
  );
}

/** Each consumer as one object, so a path can never drift from its source. */
const CONSUMERS = Object.entries(SOURCES)
  .filter(([path]) => isConsumer(path))
  .map(([path, source]) => ({ path, source }));

const CONSUMER_PATHS = CONSUMERS.map((consumer) => consumer.path);
const REACHED = new Set(
  CONSUMERS.flatMap((consumer) => importedScenarios(consumer.source)),
);

/** The module's scenario constructors — every exported function it has. */
const COMPOSERS = Object.entries(scenarios)
  .filter(([, value]) => typeof value === "function")
  .map(([name]) => name)
  .sort();

describe("the scenario module is wired to something that renders", () => {
  // The vacuity guard, and it earns its place: a glob that matched nothing, a
  // classifier that matched nothing, or an import pattern that stopped matching
  // would each turn every assertion below into a comparison of two empty sets.
  it("found the console's mocks and component tests to look in", () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(100);
    expect(CONSUMER_PATHS.filter((p) => p.includes("/api/mock")).length).toBeGreaterThan(3);
    expect(CONSUMER_PATHS.filter((p) => p.endsWith(".test.tsx")).length).toBeGreaterThan(10);
    expect(COMPOSERS.length).toBeGreaterThan(8);
    // And that the reading itself works, on a case with a known answer: slice
    // 2's pruned-measurements fixture is the worked example already on `main`.
    expect(REACHED.has("prunedMeasurements")).toBe(true);
  });

  // The other half of the vacuity guard, and the one a `.ts`/`.tsx` slip would
  // silently break. A unit test beside a mock is still a unit test; if one is
  // ever admitted, every claim above becomes satisfiable by the arrangement
  // this file was written to catch.
  it("counts no unit test as a consumer, including the ones beside mocks", () => {
    const unitTests = Object.keys(SOURCES).filter((p) => p.endsWith(".test.ts"));

    // Both of these exist and sit at a mock's own path — the exact shape the
    // obvious classifier admits by accident.
    expect(unitTests).toContain("/src/features/billing/api/mock-data.test.ts");
    expect(unitTests).toContain("/src/features/settings/api/mock.test.ts");
    expect(unitTests.filter(isConsumer)).toEqual([]);
  });

  // ⚠ THE STANDARD, over every scenario rather than over this slice's six. The
  // three slice 3 left orphaned are `costNotApplicable`, `completeTotal` and
  // `incompleteTotal`; this commit pays them, and from here a scenario added
  // without a consumer fails on the commit that adds it rather than two slices
  // later.
  //
  // ⚠ RUN AGAINST `main` AS OF THIS COMMIT'S PARENT, this assertion reports
  // exactly `costNotApplicable`, `completeTotal`, `incompleteTotal` — the three
  // ruling 10(b) names, and neither of the two it corrects the commit message
  // about. That agreement is the evidence the classifier is reading the right
  // thing; a check whose answer nobody had independently traced would be a
  // check nobody could tell from a vacuous one.
  it("leaves no canonical scenario reaching only its own unit test", () => {
    const orphaned = COMPOSERS.filter((name) => !REACHED.has(name));

    expect(orphaned).toEqual([]);
  });

  // The reachability of a scenario's ARGUMENT, which the import list cannot
  // see. `not_applicable` is one status and two economic states — the causes
  // send a reader to opposite places — so a commit that composed one of them
  // and left the other to nothing would satisfy the check above while leaving
  // half of what it owes unrendered.
  it("composes BOTH not-applicable causes somewhere that renders", () => {
    for (const reason of NOT_APPLICABLE_REASON_VALUES) {
      const call = `priceNotApplicable("${reason}")`;
      const where = CONSUMERS.filter((consumer) =>
        consumer.source.includes(call),
      ).map((consumer) => consumer.path);

      expect(where, `nothing that renders composes ${call}`).not.toEqual([]);
    }
  });

  // Every price status has a composer, and every composer is reached.
  //
  // The MAP is hand-written — there is no mechanical route from a value to the
  // function that composes it — but the LOOP is driven off the generated value
  // list, which is the half that matters: a status the registry adds tomorrow
  // has no entry here, `composer` is `undefined`, and this fails until somebody
  // writes the scenario and wires it. A hand-written four iterated over itself
  // would pass forever.
  it("reaches a composer for every price status the registry declares", () => {
    const byStatus: Partial<Record<PricingStatus, string>> = {
      known: "knownPrice",
      unknown: "unknownPrice",
      waived: "waivedPrice",
      not_applicable: "priceNotApplicable",
    };

    for (const status of PRICING_STATUS_VALUES) {
      const composer = byStatus[status];
      expect(composer, `no scenario composes \`${status}\``).toBeDefined();
      if (composer === undefined) continue;
      expect(COMPOSERS).toContain(composer);
      expect(REACHED.has(composer)).toBe(true);
    }
  });
});
