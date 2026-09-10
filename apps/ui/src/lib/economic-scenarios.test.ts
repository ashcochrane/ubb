import { describe, expect, it } from "vitest";

import {
  availableMeasurements,
  ceilingAssessment,
  chargeReceipt,
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
  CEILING_STATUS_VALUES,
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

describe("the receipt whose subject is a Charge", () => {
  const terms = {
    charge_id: "9b1c4e72-0d35-4a68-8f27-3e5a6c9d1b40",
    charged_at: "2026-06-11T08:14:02Z",
    currency: "usd",
    agreed_price_micros: 2_500_000,
    agreed_price_line_id: "5f2a7c91-3b64-4d08-9e15-7a0c2b8d4f63",
    book_version: 3,
  } as const;

  // The record is about the CHARGE, and it says so in itself rather than
  // leaving a reader to infer it from the row it happens to be stored on —
  // the inference the backend's `subject_type_of` exists to refuse.
  it("explains the Charge, not the posting it is stored on", () => {
    const scenario = chargeReceipt(terms);

    expect(scenario.pricing_receipt_subject_type).toBe("charge");
    expect(scenario.pricing_receipt.subject_type).toBe("charge");
    expect(scenario.pricing_receipt.subject_id).toBe(terms.charge_id);
    expect(scenario.pricing_receipt.effective_at).toBe(terms.charged_at);
  });

  // The shape `charge_projection.the_receipt_for` writes, key for key: both
  // methods null, both amounts settled, the regime carried by value and no
  // per-quantity line anywhere. Pinned as one object so a drift on either
  // side — the backend's writer or this composer — is a diff a reader can
  // hold against the other.
  it("names no method on either side, and carries the regime by value", () => {
    const record = chargeReceipt(terms).pricing_receipt;

    expect(record.costing).toEqual({ method: null, status: "known", detail: {} });
    expect(record.pricing).toEqual({
      method: null,
      status: "known",
      detail: { pricing_mode: "fixed" },
    });
    expect(record.totals).toEqual({ provider_cost_micros: 0, billed_cost_micros: 2_500_000 });
    expect("components" in record.pricing.detail).toBe(false);
    expect(Object.keys(record).sort()).toEqual([
      "costing",
      "currency",
      "effective_at",
      "pricing",
      "pricing_engine_version",
      "provenance",
      "receipt_schema_version",
      "subject_id",
      "subject_type",
      "totals",
    ]);
  });

  // The provenance section admits identifiers and nothing else, so the book
  // version — a number on the Pricing Book — travels as the string the
  // projection writes.
  it("carries the line that answered and the book version as identifiers", () => {
    const record = chargeReceipt(terms).pricing_receipt;

    expect(record.provenance).toEqual({
      agreed_price_line_id: terms.agreed_price_line_id,
      book_version: "3",
    });
  });

  // ⚠ THE PROPERTY THE SCENARIO EXISTS FOR. The posting's own columns are
  // returned beside the record and say the same thing it does: the price is
  // the agreed amount and settled, the supplier cost is a settled nothing,
  // and neither was derived by any method. A fixture cannot compose the
  // record and then state a different price beside it.
  it("fixes the posting's amounts to the record's totals, with no method", () => {
    const scenario = chargeReceipt(terms);

    // And the posting's instant and denomination to the record's, so a
    // consumer has nothing of its own to state beside the record.
    expect(scenario.effective_at).toBe(scenario.pricing_receipt.effective_at);
    expect(scenario.currency).toBe(scenario.pricing_receipt.currency);

    expect(scenario.billed_cost_micros).toBe(scenario.pricing_receipt.totals.billed_cost_micros);
    expect(scenario.pricing_status).toBe("known");
    expect(scenario.not_applicable_reason).toBeNull();
    expect(scenario.provider_cost_micros).toBe(scenario.pricing_receipt.totals.provider_cost_micros);
    expect(scenario.costing_status).toBe("known");
    expect(scenario.unresolved_reason).toBeNull();
    expect(scenario.pricing_method).toBeNull();

    // And the pairs are the ones the two amount scenarios already compose,
    // so a charge posting reads through every existing price and cost path.
    expect(scenario).toMatchObject(knownPrice(2_500_000));
    expect(scenario).toMatchObject(knownCost(0));
  });

  it("hands each caller its own record, so one fixture cannot edit another", () => {
    const first = chargeReceipt(terms);
    const second = chargeReceipt(terms);

    expect(first.pricing_receipt).not.toBe(second.pricing_receipt);
    expect(first.pricing_receipt.provenance).not.toBe(second.pricing_receipt.provenance);
  });
});

describe("the ceiling assessment", () => {
  // The four values the registry declares, each composed from the terms that
  // fix it, and the numbers checked against the kernel's own arithmetic
  // (`core/crossing.py`): a whole percent rounded DOWN over the KNOWN total,
  // and headroom that never goes below zero.
  it("says nothing was evaluated when no ceiling applies, and carries no figures", () => {
    const scenario = ceilingAssessment("not_applicable", { cost: incompleteTotal(900_000, 2) });

    expect(scenario.task_cogs_ceiling_micros).toBeNull();
    expect(scenario.ceiling_status).toBe("not_applicable");
    expect(scenario.ceiling_used_percentage).toBeNull();
    expect(scenario.ceiling_remaining_micros).toBeNull();
    // The row's own totals still travel — they are the same columns the
    // kernel reads, and a consumer takes all of them from here.
    expect(scenario.total_provider_cost_micros).toBe(900_000);
    expect(scenario.unresolved_event_count).toBe(2);
  });

  it("says within when every cost is known and the total is below the line", () => {
    const scenario = ceilingAssessment("within_ceiling", {
      ceiling_micros: 3_000_000,
      cost: completeTotal(2_870_000),
    });

    expect(scenario.ceiling_status).toBe("within_ceiling");
    expect(scenario.task_cogs_ceiling_micros).toBe(3_000_000);
    expect(scenario.ceiling_used_percentage).toBe(95); // 95.67, rounded down
    expect(scenario.ceiling_remaining_micros).toBe(130_000);
  });

  it("says indeterminate when the known total is below the line and something is unresolved", () => {
    const scenario = ceilingAssessment("indeterminate", {
      ceiling_micros: 3_000_000,
      cost: incompleteTotal(1_240_000, 1),
    });

    expect(scenario.ceiling_status).toBe("indeterminate");
    expect(scenario.ceiling_used_percentage).toBe(41);
    expect(scenario.ceiling_remaining_micros).toBe(1_760_000);
  });

  it("says reached at the line as well as over it, whatever remains unresolved", () => {
    const over = ceilingAssessment("ceiling_reached", {
      ceiling_micros: 800_000,
      cost: incompleteTotal(900_000, 2),
    });
    expect(over.ceiling_status).toBe("ceiling_reached");
    expect(over.ceiling_used_percentage).toBe(112);
    expect(over.ceiling_remaining_micros).toBe(0);

    // `>=`: a ceiling is reached rather than exceeded (the registry's rule).
    const at = ceilingAssessment("ceiling_reached", {
      ceiling_micros: 800_000,
      cost: completeTotal(800_000),
    });
    expect(at.ceiling_status).toBe("ceiling_reached");
    expect(at.ceiling_used_percentage).toBe(100);
    expect(at.ceiling_remaining_micros).toBe(0);
  });

  it("says a share of a zero ceiling is no share, while the ceiling is still reached", () => {
    const scenario = ceilingAssessment("ceiling_reached", {
      ceiling_micros: 0,
      cost: completeTotal(0),
    });

    expect(scenario.ceiling_used_percentage).toBeNull();
    expect(scenario.ceiling_remaining_micros).toBe(0);
  });

  // THE PROPERTY THE COMPOSER EXISTS FOR. A fixture names the state it means
  // and hands over the terms; if the registry's rule would conclude something
  // else from those terms, the fixture is describing a row the backend cannot
  // write, and it is refused at composition rather than rendered as a
  // contradiction.
  it("refuses a status the terms do not fix", () => {
    expect(() =>
      ceilingAssessment("within_ceiling", { ceiling_micros: 1_000_000, cost: incompleteTotal(1, 1) }),
    ).toThrow(/indeterminate/);
    expect(() =>
      ceilingAssessment("indeterminate", { ceiling_micros: 1_000_000, cost: completeTotal(1) }),
    ).toThrow(/within_ceiling/);
    expect(() =>
      ceilingAssessment("within_ceiling", { ceiling_micros: 1_000_000, cost: completeTotal(1_000_000) }),
    ).toThrow(/ceiling_reached/);
    expect(() =>
      ceilingAssessment("ceiling_reached", { ceiling_micros: 1_000_000, cost: completeTotal(999_999) }),
    ).toThrow(/within_ceiling/);
  });

  it("covers every status the registry declares, one composition each", () => {
    const produced = [
      ceilingAssessment("not_applicable", { cost: completeTotal(0) }),
      ceilingAssessment("within_ceiling", { ceiling_micros: 10, cost: completeTotal(1) }),
      ceilingAssessment("indeterminate", { ceiling_micros: 10, cost: incompleteTotal(1, 1) }),
      ceilingAssessment("ceiling_reached", { ceiling_micros: 10, cost: completeTotal(10) }),
    ].map((scenario) => scenario.ceiling_status);

    expect([...produced].sort()).toEqual([...CEILING_STATUS_VALUES].sort());
  });

  it("never yields a status without the three columns it was concluded from", () => {
    for (const scenario of [
      ceilingAssessment("not_applicable", { cost: completeTotal(0) }),
      ceilingAssessment("within_ceiling", { ceiling_micros: 10, cost: completeTotal(1) }),
    ]) {
      expect(Object.keys(scenario).sort()).toEqual([
        "ceiling_remaining_micros",
        "ceiling_status",
        "ceiling_used_percentage",
        "task_cogs_ceiling_micros",
        "total_provider_cost_micros",
        "unresolved_event_count",
      ]);
    }
  });
});
