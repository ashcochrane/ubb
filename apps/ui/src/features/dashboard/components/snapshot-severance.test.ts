// ⚠ **WHICH OVERVIEW SURFACE MAY READ THE ALERTING RECORD — AND IT IS EXACTLY
// ONE (#507; slice 7 §8).**
//
// The margin snapshot was DEMOTED in #502, not deleted: the record survives as
// the alerting state machine, so a webhook fires once per transition and a
// consecutive-periods rule has something to look back at. What was severed is
// every REPORTING read of its margin columns — a margin is derived at read time
// from postings, Charges and revenue records, and a stored figure computed
// before a supplier invoice arrived is one a closed period would publish
// forever.
//
// ⚠ **NO GATE WOULD CATCH A REGRESSION HERE, AND THE MARGIN IS THE FIGURE THAT
// GETS AWAY.** The three files this slice names — the customer economics table,
// its own test, and the overview page — carry no retired word and no ledger
// entry, so the forbidden-term sweep and the migration ledger are both silent
// about them whichever read they hold.
//
// The rendering assertions are not silent, but they only cover part of it, and
// the part they miss is the one that matters. The alerting row carries a
// customer id, a gross margin in micros, a margin percentage and both
// completeness counts; it carries no revenue, no provider cost and no event
// count. So a table repointed WHOLESALE reddens on the revenue and COGS columns
// it could no longer fill — but a surface that kept the one query and took only
// its MARGIN from the alerting record renders a margin of the right shape, in
// the right currency, with the right counts beside it, and every rendering
// assertion in this feature passes. That is not a hypothetical shape: #330 is
// the same fact read from two responses on one page, and it is the direction a
// severance overshoots or half-lands in. The only thing that can say it
// happened is a claim about which file holds the read.
//
// ⚠ **IT IS AN EQUALITY, WHICH IS WHAT MAKES IT BOTH DIRECTIONS.** A reporting
// surface acquiring the alerting read fails it, and so does the alert card
// LOSING it — because the card staying exactly where it is, reading alerting
// state rather than a margin report, is the other half of §8's ruling and the
// half a severing commit is most likely to overshoot.
//
// ⚠ **THE NAMES ARE DERIVED, NOT TYPED, AND THAT IS ALSO WHAT KEEPS THIS FILE
// OUT OF ITS OWN SUBJECT.** The alerting call is whichever `api.ts` function
// reaches the margin namespace, and the alerting hook is whichever `queries.ts`
// hook calls it; renaming either moves this check with it. And because no hook
// name is spelled here, the search below cannot match this file — there is no
// self-exclusion rule to get subtly wrong.

import { describe, expect, it } from "vitest";

const SOURCES = import.meta.glob("/src/features/dashboard/**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function sourceOf(path: string): string {
  const source = SOURCES[path];
  if (source === undefined) throw new Error(`no source globbed for ${path}`);
  return source;
}

/** Each exported function in a module, with its body up to the next one. */
function exportedFunctions(source: string): { name: string; body: string }[] {
  const starts = [...source.matchAll(/export (?:async )?function (\w+)/g)];
  return starts.map((match, index) => ({
    name: match[1] ?? "",
    body: source.slice(
      match.index ?? 0,
      starts[index + 1]?.index ?? source.length,
    ),
  }));
}

const API = sourceOf("/src/features/dashboard/api/api.ts");
const QUERIES = sourceOf("/src/features/dashboard/api/queries.ts");
const API_CALLS = exportedFunctions(API);

/** The route the nine collapsed reports became. */
const ONE_QUERY = '"/analytics/economics"';

/**
 * The calls that reach the alerting record: the margin namespace client is the
 * only door to it from this feature, and after the collapse it opens on one
 * route.
 */
const ALERTING_CALLS = API_CALLS.filter((fn) =>
  fn.body.includes("marginApi"),
).map((fn) => fn.name);

/**
 * The calls that ask the one query — and the ones that ask it THROUGH another,
 * which is why this closes rather than filters once. `getCustomerEconomics` is
 * the whole reason: it is the per-customer margin list, it names no route at
 * all, and a one-pass filter would leave the most load-bearing read of the
 * three out of the set that is supposed to contain it.
 */
function callsTheOneQuery(): string[] {
  let reached = API_CALLS.filter((fn) => fn.body.includes(ONE_QUERY)).map(
    (fn) => fn.name,
  );
  for (let pass = 0; pass < API_CALLS.length; pass++) {
    const next = API_CALLS.filter(
      (fn) =>
        fn.body.includes(ONE_QUERY) ||
        reached.some(
          (name) =>
            name !== fn.name && new RegExp(`\\b${name}\\(`).test(fn.body),
        ),
    ).map((fn) => fn.name);
    if (next.length === reached.length) return next;
    reached = next;
  }
  return reached;
}

const ONE_QUERY_CALLS = callsTheOneQuery();

/** Every hook, by which of the two reads its `queryFn` goes through. */
const HOOKS = exportedFunctions(QUERIES).filter((fn) =>
  fn.body.includes("dashboardApi."),
);
const hooksReaching = (calls: string[]) =>
  HOOKS.filter((hook) =>
    calls.some((call) => hook.body.includes(`dashboardApi.${call}(`)),
  ).map((hook) => hook.name);

const ALERTING_HOOKS = hooksReaching(ALERTING_CALLS);
const ONE_QUERY_HOOKS = hooksReaching(ONE_QUERY_CALLS);

/** Every rendering surface of this feature, and its own test beside it. */
const SURFACES = Object.keys(SOURCES).filter((path) =>
  path.startsWith("/src/features/dashboard/components/"),
);

const namesAny = (source: string, names: string[]) =>
  names.some((name) => new RegExp(`\\b${name}\\b`).test(source));

describe("the overview's margin figures come from the one query", () => {
  // The vacuity floor. Every assertion below is a claim about sets this file
  // computes, and each of the three could go empty on a rename — an empty
  // `ALERTING_CALLS` would make the equality read "no surface holds the read",
  // which is exactly the sentence a severing commit wants to hear.
  it("found the feature's calls, its hooks and its surfaces", () => {
    expect(ALERTING_CALLS).toHaveLength(1);
    expect(ALERTING_HOOKS).toHaveLength(1);
    expect(ONE_QUERY_HOOKS.length).toBeGreaterThan(3);
    expect(SURFACES.length).toBeGreaterThan(8);
    // The per-customer margin list reaches the one query through another call
    // and names no route, so it is the member the closure exists for and the
    // one a simpler derivation drops.
    expect(ONE_QUERY_CALLS).toContain("getCustomerEconomics");
    // Two reads, and nothing may be both — an overlap would make every
    // assertion below satisfiable from either side at once.
    expect(
      ONE_QUERY_HOOKS.filter((name) => ALERTING_HOOKS.includes(name)),
    ).toEqual([]);
    // And the feature's other reads — api keys, pricing books, Connect — are
    // neither, so naming one of them satisfies nothing here.
    expect(HOOKS.length).toBeGreaterThan(
      ONE_QUERY_HOOKS.length + ALERTING_HOOKS.length,
    );
  });

  // ⚠ THE EQUALITY, AND BOTH DIRECTIONS OF IT.
  it("leaves the alerting read with exactly one surface — the alert card", () => {
    const holders = SURFACES.filter((path) =>
      namesAny(sourceOf(path), ALERTING_HOOKS),
    );

    expect(holders).toEqual([
      "/src/features/dashboard/components/unprofitable-alert.tsx",
    ]);
  });

  // The three §8 names, said one at a time so a failure says which one moved.
  // Their positive half: each takes its figures from the one query, the first
  // two by holding one of its hooks and the third by rendering a component that
  // does — which is why it may import no api module of its own.
  it("has the customer economics table reading the one query and nothing else", () => {
    const source = sourceOf(
      "/src/features/dashboard/components/customer-economics-table.tsx",
    );

    expect(namesAny(source, ONE_QUERY_HOOKS)).toBe(true);
    expect(namesAny(source, ALERTING_HOOKS)).toBe(false);
  });

  it("has the overview page reading the one query and nothing else", () => {
    const source = sourceOf(
      "/src/features/dashboard/components/overview-page.tsx",
    );

    expect(namesAny(source, ONE_QUERY_HOOKS)).toBe(true);
    expect(namesAny(source, ALERTING_HOOKS)).toBe(false);
  });

  // ⚠ A TEST IS A READER TOO, and the one this slice names is the reason to say
  // so: a rendering assertion fed from a hand-built snapshot row would render
  // the severed figure back into a green suite. It imports the component and
  // the component alone, so everything it renders arrives through the feature's
  // provider — and a stub of the alerting read would have to import the api
  // module to install one.
  it("has the table's test taking everything through the provider", () => {
    const source = sourceOf(
      "/src/features/dashboard/components/customer-economics-table.test.tsx",
    );

    expect(namesAny(source, ALERTING_HOOKS)).toBe(false);
    expect(source).not.toMatch(/from "\.\.\/api\//);
    expect(source).toMatch(/from "\.\/customer-economics-table"/);
  });
});
