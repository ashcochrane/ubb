// The discovery contract: which axes THIS tenant may group by (#506; slice 7 §7).
//
// `GET /metering/analytics/grouping-options` is computed per tenant and is
// never a shipped list — map #137 constraint 5 is explicit that UBB ships no
// catalogue of its tenants' vocabulary, and a discovery endpoint answering a
// fixed set of axes would be UBB shipping one. The two ROLLUP axes are UBB's
// and closed; the FIELDS are the tenant's and open, so two workspaces opening
// the same picker see two different lists.
//
// ⚠ **ONE HOOK AND ONE KEY, FOR TWO PICKERS.** The events chart and the
// dashboard breakdown ask the same question, and two hooks issuing one request
// under two keys would be two cache entries for one answer — they would refetch
// independently and could disagree about what a tenant may group by while both
// are on screen. The key is the route's, so a mutation that changes the
// declared registry invalidates it by prefix like any other.
//
// ⚠ **A PICKER'S OPTIONS ARE A SUBSET OF THIS, NEVER A DIFFERENT LIST.** Each
// row carries `supported_surfaces` and `unsupported_measures`, which is the
// mechanism §7 built so an axis can ship with a measure declared unsupported
// and the reason stated. Narrowing happens at the call site with
// `optionsForSurface`; inventing a list beside this one is the thing the
// contract exists to stop.

import { queryOptions, useQuery } from "@tanstack/react-query";

import { meteringApi } from "@/api/client";
import { unwrap } from "@/api/problem";
import { API_PROVIDER, mockDelay } from "@/lib/api-provider";
import { ANALYTICS_ROLLUP_VALUES } from "@/lib/vocabulary";
import type { GroupingOption, UbbAxis } from "@/lib/grouping-axis";
import { axisRequestWord, FIELD_KIND, ROLLUP_KIND } from "@/lib/grouping-axis";

/** The surface an axis is being offered for, as the contract spells it. */
export const ANALYTICS_SURFACE = "analytics";

/**
 * The other one: the grouping a tenant's invoice LINES are built on.
 *
 * ⚠ **A NARROWER SET THAN ANALYTICS, AND THE DIFFERENCE IS MONEY.** An axis
 * resolving at the measurement grain is analytics-only, because an invoice line
 * is money and UBB holds none at that grain — so the two pickers reading this
 * one contract genuinely see two lists. Spelled here rather than at the call
 * site so the invoice surface and the fixtures that describe it cannot drift
 * apart on a string.
 */
export const INVOICE_LINES_SURFACE = "invoice_lines";

/**
 * The mock workspace's own declared axis keys, in slot order.
 *
 * ⚠ **ONE LIST, READ BY BOTH MOCKS THAT NEED IT.** The pricing feature's rule
 * editor reads the declared registry and builds its own `GroupingFieldDef`
 * rows from these same keys, so a mock tenant that declared `model` to one
 * surface and `dim1` to another would be two tenants wearing one name — which
 * is precisely the defect that let the group-by picker offer slot names for
 * years. The events fixtures report values on three of them.
 */
export const MOCK_DECLARED_AXIS_KEYS = [
  "model",
  "region",
  "environment",
  "team",
  "workflow",
  "channel",
  "tier",
  "deployment",
  "pipeline",
  "cohort",
] as const;

function mockOption(over: Partial<GroupingOption> & { key: string }): GroupingOption {
  return {
    kind: FIELD_KIND,
    label: "",
    rollup: null,
    source_grain: "event",
    supported_surfaces: [ANALYTICS_SURFACE, INVOICE_LINES_SURFACE],
    unsupported_measures: [],
    max_cardinality: null,
    ...over,
  };
}

/**
 * The grain each axis UBB reserves resolves at.
 *
 * ⚠ **A `Record` OVER THE CONSOLE'S OWN UNION RATHER THAN A LIST, so the five
 * are not written out a third time.** `UBB_AXIS_TITLES` is the set, and
 * `tests/contracts/test_grouping_axis_vocabulary.py` holds that set equal to
 * the server's `RESERVED_KEYS` — so a sixth reserved axis reddens there AND
 * fails `tsc` here, instead of being a word the mock quietly never offers.
 * Which grain each one resolves at is the server's `ALWAYS_PRESENT_AXES`,
 * mirrored because a fixture has to state it and nothing generates it.
 */
const RESERVED_AXIS_GRAIN: Record<UbbAxis, string> = {
  customer: "event",
  provider: "event",
  event_type: "event",
  task_type: "task",
  subtask_type: "subtask",
};

/**
 * What each rollup axis answers for, where it is not the ordinary case.
 *
 * The measurement-concept rollup ships with the supplier cost declared
 * UNSUPPORTED and the reason stated (§7): the measurement record carries
 * quantities and no cost lines, and declaring an unsupported measure is the
 * honest answer the capability mechanism was built to express. A fixture that
 * left it supported would describe a server that does not exist.
 *
 * A `Record` over the generated union rather than a partial one, so a rollup
 * the registry declares tomorrow is a `tsc` failure here rather than a row
 * that quietly claims the ordinary case on a grain nobody checked.
 */
const ROLLUP_MOCK_DETAIL: Record<
  (typeof ANALYTICS_ROLLUP_VALUES)[number],
  Partial<GroupingOption>
> = {
  event_category: {},
  measurement_concept: {
    source_grain: "measurement",
    // Measurement quantities only — an invoice line is money, and UBB holds
    // none at this grain.
    supported_surfaces: [ANALYTICS_SURFACE],
    unsupported_measures: [{
      measure: "supplier_cogs",
      reason:
        "A measurement record carries quantities and no cost lines, so a cost "
        + "at this grain could only be produced by spreading an event's cost "
        + "across the measurements it contains.",
    }],
  },
};

/**
 * What the mock workspace answers — the five reserved axes, its ten declared
 * fields, then the rollups, in the order the server returns them.
 */
export const MOCK_GROUPING_OPTIONS: GroupingOption[] = [
  ...(Object.keys(RESERVED_AXIS_GRAIN) as UbbAxis[]).map((axis) =>
    mockOption({
      key: axisRequestWord({ kind: FIELD_KIND, name: axis }),
      source_grain: RESERVED_AXIS_GRAIN[axis],
    })),
  ...MOCK_DECLARED_AXIS_KEYS.map((key) =>
    mockOption({
      key: axisRequestWord({ kind: FIELD_KIND, name: key }),
      label: key,
      max_cardinality: 200,
    })),
  // ⚠ DERIVED FROM THE REGISTRY'S OWN SET, so a rollup declared tomorrow is on
  // offer in mock mode the day it is generated. A hand-written pair here would
  // be a third copy of a closed set the registry already owns, and the one most
  // likely to be forgotten.
  ...ANALYTICS_ROLLUP_VALUES.map((rollup) =>
    mockOption({
      key: axisRequestWord({ kind: ROLLUP_KIND, name: rollup }),
      kind: ROLLUP_KIND,
      rollup,
      ...ROLLUP_MOCK_DETAIL[rollup],
    })),
];

async function fetchGroupingOptions(): Promise<GroupingOption[]> {
  if (API_PROVIDER === "mock") {
    await mockDelay();
    return MOCK_GROUPING_OPTIONS;
  }
  const answer = unwrap(await meteringApi.GET("/analytics/grouping-options"));
  return answer.options;
}

export const groupingOptionsQueryOptions = queryOptions({
  queryKey: ["metering", "analytics", "grouping-options"] as const,
  queryFn: fetchGroupingOptions,
  // The declared registry changes when a tenant edits it, not while a chart is
  // on screen; the same five minutes the workspace config takes.
  staleTime: 5 * 60_000,
});

/** Every axis this tenant may group by, on any surface. */
export function useGroupingOptions() {
  return useQuery(groupingOptionsQueryOptions);
}

/**
 * The axes offered for one surface, in the contract's own order.
 *
 * ⚠ **A ROW THAT DOES NOT NAME THE SURFACE IS NOT OFFERED ON IT.** That is the
 * contract's own rule rather than a convenience: an axis resolving at the
 * measurement grain is analytics-only, because an invoice line is money and
 * there is none at that grain. Reading past it would put an axis in a picker
 * whose request the server refuses.
 */
export function optionsForSurface(
  options: readonly GroupingOption[] | undefined,
  surface: string,
): GroupingOption[] {
  return (options ?? []).filter(
    (option) => option.supported_surfaces.includes(surface));
}

// ⚠ NARROWING BY MEASURE IS DELIBERATELY NOT HERE YET. Each row carries
// `unsupported_measures`, and capability is declared BY EXCEPTION — every
// measure not named is accepted and answers with its own state. Writing the
// filter now would be a helper with no caller, and the surface that will want
// it is the one that renders the five measure states (#510); it can own the
// reading of those exceptions along with the states they produce.
