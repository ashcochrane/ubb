import { describe, expect, it } from "vitest";

import {
  availableMeasurements,
  completePriceTotal,
  completeTotal,
  costNotApplicable,
  incompletePriceTotal,
  incompleteTotal,
  knownCost,
  knownPrice,
  measurementsNotApplicable,
  priceNotApplicable,
  prunedMeasurements,
  unknownCost,
  unknownPrice,
  waivedPrice,
} from "./economic-scenarios";
import { isPartial, supplierCostTotal } from "./supplier-cost";
import {
  COSTING_STATUS_VALUES,
  MEASUREMENTS_STATUS_VALUES,
  NOT_APPLICABLE_REASON_VALUES,
  PRICING_STATUS_VALUES,
} from "./vocabulary";

describe("measurement scenarios", () => {
  it("carries the recorded quantities, and says they can be read", () => {
    const scenario = availableMeasurements({
      input_tokens: 4200,
      output_tokens: 1730,
    });

    expect(scenario.measurements).toEqual({
      input_tokens: 4200,
      output_tokens: 1730,
    });
    expect(scenario.measurements_status).toBe("available");
  });

  it("says an empty bag is a REMOVAL when the detail was pruned", () => {
    const scenario = prunedMeasurements();

    expect(scenario.measurements).toEqual({});
    expect(scenario.measurements_status).toBe("pruned");
  });

  it("says an empty bag is an ABSENCE when the posting was never measured", () => {
    const scenario = measurementsNotApplicable();

    expect(scenario.measurements).toEqual({});
    expect(scenario.measurements_status).toBe("not_applicable");
  });

  // The property the module exists for. Two of the three states carry the same
  // empty bag, so the bag alone cannot say which one a fixture meant — that
  // ambiguity is the whole defect `measurements_status` was coined to end
  // (`domain-vocabulary/concepts/economics.yaml`). Binding the two facts into
  // one returned object is what stops a fixture author restating half of it.
  it("never yields a bag without the status that says what it means", () => {
    const scenarios = [
      availableMeasurements({ input_tokens: 1 }),
      prunedMeasurements(),
      measurementsNotApplicable(),
    ];

    for (const scenario of scenarios) {
      expect(Object.keys(scenario)).toEqual([
        "measurements",
        "measurements_status",
      ]);
    }
  });

  // Driven off the generated value list rather than a hand-written trio: the
  // registry declares `measurements_status` CLOSED and complete, so a value
  // arriving here with no scenario behind it is a state no console fixture can
  // represent — which is exactly the gap #155 §9.2 makes a slice pay for.
  it("covers every state the registry declares, one scenario each", () => {
    const produced = [
      availableMeasurements({}),
      prunedMeasurements(),
      measurementsNotApplicable(),
    ].map((scenario) => scenario.measurements_status);

    expect([...produced].sort()).toEqual([...MEASUREMENTS_STATUS_VALUES].sort());
  });

  it("hands each caller its own object, so one fixture cannot edit another", () => {
    const first = prunedMeasurements();
    const second = prunedMeasurements();

    expect(first).not.toBe(second);
    expect(first.measurements).not.toBe(second.measurements);
  });
});

describe("supplier cost scenarios", () => {
  it("carries the amount, and says UBB knows it", () => {
    const scenario = knownCost(4_200_000);

    expect(scenario.provider_cost_micros).toBe(4_200_000);
    expect(scenario.costing_status).toBe("known");
    expect(scenario.unresolved_reason).toBeNull();
  });

  it("says a NULL amount is UNLEARNED, and names what would settle it", () => {
    const scenario = unknownCost("cost_rate_missing");

    expect(scenario.provider_cost_micros).toBeNull();
    expect(scenario.costing_status).toBe("unresolved");
    expect(scenario.unresolved_reason).toBe("cost_rate_missing");
  });

  it("says a NULL amount is a NON-COST when the type declares none", () => {
    const scenario = costNotApplicable();

    expect(scenario.provider_cost_micros).toBeNull();
    expect(scenario.costing_status).toBe("not_applicable");
    expect(scenario.unresolved_reason).toBeNull();
  });

  // The property the trio exists for, and the one an `?? 0` would break. Two of
  // the three states carry the same NULL amount, so the amount alone cannot say
  // which one a fixture meant — and the two mean opposite things about whether
  // anything is missing from the totals built over them.
  it("never yields an amount without the status that says what it means", () => {
    for (const scenario of [
      knownCost(1),
      unknownCost("reported_cost_missing"),
      costNotApplicable(),
    ]) {
      expect(Object.keys(scenario)).toEqual([
        "provider_cost_micros",
        "costing_status",
        "unresolved_reason",
      ]);
    }
  });

  // Every combination below is one the database admits: the posting's own
  // `ck_posting_costing_status_agrees_with_the_cost` refuses an amount beside
  // `unresolved`, and refuses a reason beside either of the other two.
  it("composes only the three rows the posting's constraint admits", () => {
    for (const scenario of [
      knownCost(1),
      unknownCost("measurement_not_declared"),
      costNotApplicable(),
    ]) {
      const settled = scenario.costing_status === "known";
      expect(scenario.provider_cost_micros === null).toBe(!settled);
      expect(scenario.unresolved_reason === null).toBe(
        scenario.costing_status !== "unresolved",
      );
    }
  });

  // Driven off the generated value list for the same reason the measurement
  // trio is: the registry declares `costing_status` CLOSED, so a value arriving
  // with no scenario behind it is a state no console fixture can represent.
  it("covers every costing status the registry declares, one scenario each", () => {
    const produced = [
      knownCost(0),
      unknownCost("cost_rate_missing"),
      costNotApplicable(),
    ].map((scenario) => scenario.costing_status);

    expect([...produced].sort()).toEqual([...COSTING_STATUS_VALUES].sort());
  });
});

describe("customer price scenarios", () => {
  it("carries the amount, and says UBB resolved it", () => {
    const scenario = knownPrice(4_200_000);

    expect(scenario.billed_cost_micros).toBe(4_200_000);
    expect(scenario.pricing_status).toBe("known");
  });

  // ⚠ THE PROPERTY THE FOUR EXIST FOR, and the one that differs from the cost
  // side: THREE of the four states carry the same NULL amount, not two. The
  // amount cannot say which a fixture meant, and the three mean different
  // things about whether anything is missing — only `unknown` is.
  it("says a NULL amount is three different states, told apart by the status", () => {
    const absent = [
      unknownPrice(),
      waivedPrice(),
      priceNotApplicable("fixed_task_pricing"),
    ];

    for (const scenario of absent) {
      expect(scenario.billed_cost_micros).toBeNull();
    }
    expect(absent.map((scenario) => scenario.pricing_status)).toEqual([
      "unknown",
      "waived",
      "not_applicable",
    ]);
  });

  it("never yields an amount without the status that says what it means", () => {
    for (const scenario of [
      knownPrice(1),
      unknownPrice(),
      waivedPrice(),
      priceNotApplicable("tenant_not_billing"),
    ]) {
      expect(Object.keys(scenario)).toEqual([
        "billed_cost_micros",
        "pricing_status",
        "not_applicable_reason",
      ]);
    }
  });

  // ⚠ THE SIXTH AND SEVENTH STATES THIS SLICE INTRODUCES, and the reason the
  // reason is an ARGUMENT rather than a constant. `not_applicable` says a price
  // does not apply; it does not say why, and a reader given only that goes
  // looking for a number nobody wrote. The two causes send them to opposite
  // places — one to the Task's own charge, one nowhere at all — so a scenario
  // that fixed the reason would make half of this slice's owed states
  // unreachable from any fixture.
  it("names WHY a price does not apply, and both causes are composable", () => {
    for (const reason of NOT_APPLICABLE_REASON_VALUES) {
      const scenario = priceNotApplicable(reason);

      expect(scenario.billed_cost_micros).toBeNull();
      expect(scenario.pricing_status).toBe("not_applicable");
      expect(scenario.not_applicable_reason).toBe(reason);
    }
  });

  // Read only where the status is `not_applicable`, exactly as the registry
  // says: a reason beside any other status would be a row describing a cause
  // for an absence that has one of its own.
  it("carries a reason on the one status the registry reads it under", () => {
    for (const scenario of [
      knownPrice(1),
      unknownPrice(),
      waivedPrice(),
      priceNotApplicable("fixed_task_pricing"),
    ]) {
      expect(scenario.not_applicable_reason === null).toBe(
        scenario.pricing_status !== "not_applicable",
      );
    }
  });

  // Every combination is one the database admits: the posting's own
  // `ck_posting_pricing_status_agrees_with_the_price` refuses an amount beside
  // any status but `known`.
  it("composes only the rows the posting's constraint admits", () => {
    for (const scenario of [
      knownPrice(1),
      unknownPrice(),
      waivedPrice(),
      priceNotApplicable("tenant_not_billing"),
    ]) {
      const settled = scenario.pricing_status === "known";
      expect(scenario.billed_cost_micros === null).toBe(!settled);
    }
  });

  // Driven off the generated value list, for the reason its two siblings are:
  // `pricing_status` is CLOSED, so a value arriving with no scenario behind it
  // is a state no console fixture can represent.
  it("covers every pricing status the registry declares, one scenario each", () => {
    const produced = [
      knownPrice(0),
      unknownPrice(),
      waivedPrice(),
      priceNotApplicable("fixed_task_pricing"),
    ].map((scenario) => scenario.pricing_status);

    expect([...produced].sort()).toEqual([...PRICING_STATUS_VALUES].sort());
  });
});

describe("cost total scenarios", () => {
  it("says a total that left nothing out is whole", () => {
    const scenario = completeTotal(4_200_000);

    expect(scenario.unresolved_event_count).toBe(0);
    expect(isPartial(scenario)).toBe(false);
  });

  it("says a total that skipped events is a floor, and how many it skipped", () => {
    const scenario = incompleteTotal(4_200_000, 3);

    expect(scenario.unresolved_event_count).toBe(3);
    expect(isPartial(scenario)).toBe(true);
  });

  // The rendering assertion §9.2 asks for beside the fixture: the state has to
  // render as ITSELF, and the defect it guards is one line long
  // (`const displayed = amount ?? 0`).
  it("renders an incomplete total as a floor rather than as a figure", () => {
    expect(supplierCostTotal(4_200_000, completeTotal(4_200_000), "usd")).toBe(
      "$4.20",
    );
    expect(
      supplierCostTotal(4_200_000, incompleteTotal(4_200_000, 3), "usd"),
    ).toBe("at least $4.20");
  });

  // AC 2 at its sharpest, composed rather than hand-built: a window UBB knows
  // no cost in at all must not render the zero its floor really is.
  it("renders no amount at all when every cost in the window is unknown", () => {
    const nothingKnown = incompleteTotal(0, 5);

    expect(supplierCostTotal(nothingKnown.micros, nothingKnown, "usd")).toBe(
      "—",
    );
  });
});

describe("customer price total scenarios", () => {
  it("says a billed total that left nothing out is whole", () => {
    const scenario = completePriceTotal(620_000);

    expect(scenario.micros).toBe(620_000);
    expect(scenario.unpriced_event_count).toBe(0);
  });

  it("says a billed total that skipped events is a floor, and how many it skipped", () => {
    const scenario = incompletePriceTotal(620_000, 3);

    expect(scenario.micros).toBe(620_000);
    expect(scenario.unpriced_event_count).toBe(3);
  });

  // The rendering assertion §9.2 asks for sits where the console first renders
  // this total — the runs surface's component tests, against the runs mock
  // that composes these scenarios (#424). No `lib/` renderer reads the price
  // side yet, so there is nothing at this altitude to assert against.
});
