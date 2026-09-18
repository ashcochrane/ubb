// ⚠ **WHERE THE CUSTOMER'S MARGIN TREND GETS ITS FIGURES — AND WHERE IT MAY
// NOT (#508; slice 7 §8, §19's customers row).**
//
// The trend used to read N stored monthly margin snapshots, one row per closed
// period. #502 DEMOTED that record to alerting state and #501 moved this read
// onto the one economic query, which derives each month from the facts as they
// stand — so a month whose supplier invoice arrived late answers differently
// the next time it is asked, instead of publishing forever the figure that
// happened to be computable when the period closed.
//
// ⚠ **NOTHING ELSE WOULD SAY IF IT CAME BACK.** This feature carries no retired
// word for the snapshot and no ledger entry, so the forbidden-term sweep and
// the migration ledger are both silent about which read a chart holds. The
// rendering assertions are nearly silent too: a trend point is a period, a
// cost, a revenue and a margin, and the alerting record can fill the period and
// the margin — so a chart that kept the one query for cost and revenue and took
// only its MARGIN from the alerting row would draw three plausible lines and
// pass every rendering test in this feature. The only thing that can say it
// happened is a claim about which route the call reaches.
//
// ⚠ **BOTH DIRECTIONS, AND THE NEGATIVE ONE IS A FEATURE-WIDE EQUALITY.** The
// positive: the trend's call asks the one query, bucketed by month. The
// negative: NO call in this feature reaches the alerting route at all — which
// is stronger than checking the trend alone, because a second read installed
// beside it and summed in would satisfy a per-call check.
//
// ⚠ **"READS THE MARGIN NAMESPACE" IS NOT THE TEST, AND ON THIS FEATURE IT
// CANNOT BE.** The dashboard's severance check could filter on the margin
// client because that feature's only margin-namespace call WAS the alerting
// one. Here three calls legitimately use it — the business rollup, which §1
// rules keeps its own contract, and the supplied-revenue pair this ticket
// built. So the discriminator is the ROUTE, which is what actually
// distinguishes a report from an alert.
//
// ⚠ **THE NAMES ARE DERIVED, NOT TYPED, which is also what keeps this file out
// of its own subject.** The trend call is whichever `api.ts` function asks the
// one query with a month bucket, and the trend hook is whichever `queries.ts`
// hook calls it; renaming either moves this check with it, and because no hook
// or function name is spelled below, the search cannot match this file.

import { describe, expect, it } from "vitest";

const SOURCES = import.meta.glob("/src/features/customers/**/*.{ts,tsx}", {
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

const API = sourceOf("/src/features/customers/api/api.ts");
const QUERIES = sourceOf("/src/features/customers/api/queries.ts");
const API_CALLS = exportedFunctions(API);

/** The route the nine collapsed reports became. */
const ONE_QUERY = '"/analytics/economics"';

/**
 * The alerting record's own route — the one thing #502 left the snapshot
 * serving, and the one a reporting surface may not read.
 */
const ALERTING_ROUTE = '"/unprofitable"';

/** The calls that ask the one query at MONTH bucketing. */
const MONTHLY_CALLS = API_CALLS.filter(
  (fn) => fn.body.includes(ONE_QUERY) && /bucket:\s*"month"/.test(fn.body),
).map((fn) => fn.name);

/** Every call in this feature that asks the one query, at any grain. */
const ONE_QUERY_CALLS = API_CALLS.filter((fn) =>
  fn.body.includes(ONE_QUERY),
).map((fn) => fn.name);

/** Every hook whose `queryFn` goes through one of these calls. */
const HOOKS = exportedFunctions(QUERIES).filter((fn) =>
  fn.body.includes("customersApi."),
);
const hooksReaching = (calls: string[]) =>
  HOOKS.filter((hook) =>
    calls.some((call) => hook.body.includes(`customersApi.${call}(`)),
  ).map((hook) => hook.name);

const MONTHLY_HOOKS = hooksReaching(MONTHLY_CALLS);

/** Every rendering surface of this feature. */
const SURFACES = Object.keys(SOURCES).filter((path) =>
  path.startsWith("/src/features/customers/components/"),
);

const namesAny = (source: string, names: string[]) =>
  names.some((name) => new RegExp(`\\b${name}\\b`).test(source));

describe("the customer's margin trend reads the one query", () => {
  // The vacuity floor. Every claim below is about sets this file computes, and
  // an empty one would make the negative assertions read "nothing reads
  // anything" — the sentence a regression would most like to hear.
  it("found this feature's calls, its hooks and its surfaces", () => {
    expect(API_CALLS.length).toBeGreaterThan(20);
    expect(HOOKS.length).toBeGreaterThan(15);
    expect(SURFACES.length).toBeGreaterThan(10);
    // Several reads ask the one query — the list, one customer, the day series
    // — and exactly one of them buckets by month. Two would mean the trend has
    // acquired a twin, which is how two surfaces start disagreeing.
    expect(ONE_QUERY_CALLS.length).toBeGreaterThan(2);
    expect(MONTHLY_CALLS).toHaveLength(1);
    expect(MONTHLY_HOOKS).toHaveLength(1);
  });

  // ⚠ THE NEGATIVE DIRECTION, FEATURE-WIDE. Not "the trend does not read it"
  // but "nothing here does", so a second read installed beside the trend and
  // summed into its points fails as loudly as a repointed one.
  it("reaches the alerting record from no call in this feature", () => {
    const readers = API_CALLS.filter((fn) => fn.body.includes(ALERTING_ROUTE));

    expect(readers.map((fn) => fn.name)).toEqual([]);
  });

  // ⚠ AND THE MARGIN NAMESPACE IS STILL REACHED, WHICH IS WHY THE ROUTE IS THE
  // DISCRIMINATOR AND THE CLIENT IS NOT. Were this feature to stop using the
  // margin client altogether, the assertion above would pass for the wrong
  // reason — it would be true of a feature that had lost the business rollup
  // and the supplied-revenue pair too.
  it("still reaches the margin namespace for the reads that legitimately do", () => {
    const marginCalls = API_CALLS.filter((fn) => fn.body.includes("marginApi"));

    expect(marginCalls.length).toBeGreaterThanOrEqual(3);
    // None of them is the alerting one — the same fact from the other side.
    expect(marginCalls.filter((fn) => fn.body.includes(ALERTING_ROUTE))).toEqual([]);
  });

  // ⚠ THE POSITIVE DIRECTION, AND THE EQUALITY THAT MAKES IT BOTH. Exactly one
  // surface holds the monthly read, and it is the tab that renders the trend —
  // so the tab LOSING it fails this as surely as a second surface gaining it.
  it("leaves the monthly read with exactly one surface — the overview tab", () => {
    const holders = SURFACES.filter((path) =>
      namesAny(sourceOf(path), MONTHLY_HOOKS),
    );

    expect(holders).toEqual([
      "/src/features/customers/components/overview-tab.tsx",
    ]);
  });

  // The chart itself takes points as a prop and asks nothing: it may hold no
  // read at all, which is what makes the equality above a complete statement
  // about where the figures come from.
  it("has the trend chart holding no read of its own", () => {
    const source = sourceOf(
      "/src/features/customers/components/margin-trend-chart.tsx",
    );

    expect(source).not.toMatch(/from "\.\.\/api\/queries"/);
    expect(namesAny(source, MONTHLY_HOOKS)).toBe(false);
  });
});
