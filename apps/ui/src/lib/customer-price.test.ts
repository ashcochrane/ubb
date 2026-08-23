import { describe, expect, it } from "vitest";

import {
  NOT_APPLICABLE_REASON_EXPLANATIONS,
  PRICING_STATUS_EXPLANATIONS,
  customerPriceAmount,
  customerPriceExplanation,
  notApplicableReasonLabel,
  pricingMethodLabel,
  pricingStatusLabel,
  settledPriceMicros,
} from "./customer-price";
import {
  priceNotApplicable,
  unknownPrice,
  waivedPrice,
  knownPrice,
} from "./economic-scenarios";
import { missingLabel } from "./localisation";
import {
  NOT_APPLICABLE_REASON_LABEL_KEYS,
  NOT_APPLICABLE_REASON_VALUES,
  PRICING_METHOD_LABEL_KEYS,
  PRICING_METHOD_VALUES,
  PRICING_STATUS_LABEL_KEYS,
  PRICING_STATUS_VALUES,
} from "./vocabulary";

/** Anything that reads as an amount of money, in any of the console's shapes. */
const CURRENCY = /[$£€]\s*-?[\d,]/;

// ⚠ THE METHOD'S BINDING MOVED INTO THE MODULE UNDER TEST (#372), AND THIS
// TEST NOW IMPORTS IT RATHER THAN REBUILDING IT. It was bound here in #371
// because nothing rendered a method yet and a label with no call site is a dead
// export a later reader has to classify. #372 is the surface — two of them, in
// fact, which is what put the binding in `lib/` — so a second `labelMap` here
// would be a copy of the thing under test, and a test that built its own copy
// could not fail if the real one were bound to the wrong concept.

describe("the price side's words come from the catalogue", () => {
  // ⚠ THE ASSERTION THE LABEL HALF OF THIS TICKET EXISTS FOR. A word that is
  // "there" but is the localisation layer's development placeholder is a value
  // the catalogue does not carry, and it renders on the page as `[no label:
  // pricing_status.waived]`. Asserting the label is non-empty would pass on it.
  it.each([
    ["pricing_status", PRICING_STATUS_VALUES, PRICING_STATUS_LABEL_KEYS, pricingStatusLabel],
    [
      "not_applicable_reason",
      NOT_APPLICABLE_REASON_VALUES,
      NOT_APPLICABLE_REASON_LABEL_KEYS,
      notApplicableReasonLabel,
    ],
    ["pricing_method", PRICING_METHOD_VALUES, PRICING_METHOD_LABEL_KEYS, pricingMethodLabel],
  ] as const)("carries wording for every %s the registry declares", (_concept, values, keys, label) => {
    for (const value of values) {
      const key: string = keys[value as keyof typeof keys];
      // Derived from the concept's declared label prefix, never written in
      // English here: the key IS the registry's, and the words hang off it.
      expect(key).toMatch(new RegExp(`^${_concept}\\.`));
      expect(label(value)).not.toBe(missingLabel(key));
      expect(label(value).trim()).not.toBe("");
    }
  });

  // The registry's own rule, asserted rather than trusted: `waived` is a
  // decision and `unknown` is information UBB does not have, and neither is an
  // amount. A catalogue entry that read "£0.00" would satisfy every "has
  // wording" check ever written.
  it("never gives an absent price a word that reads as money", () => {
    for (const status of PRICING_STATUS_VALUES) {
      if (status === "known") continue;
      expect(pricingStatusLabel(status)).not.toMatch(CURRENCY);
    }
  });

  // AC 5. The two causes are mutually exclusive and send the reader to
  // OPPOSITE places, so two labels that happened to coincide would be a screen
  // that answers "why is there no price here?" with one answer for two
  // questions.
  it("tells the two not-applicable reasons apart, in words and in sentences", () => {
    const words = NOT_APPLICABLE_REASON_VALUES.map(notApplicableReasonLabel);
    expect(new Set(words).size).toBe(NOT_APPLICABLE_REASON_VALUES.length);

    const sentences = NOT_APPLICABLE_REASON_VALUES.map(
      (reason) => NOT_APPLICABLE_REASON_EXPLANATIONS[reason],
    );
    expect(new Set(sentences).size).toBe(NOT_APPLICABLE_REASON_VALUES.length);
  });

  it("renders a value the registry has never seen as the token the server sent", () => {
    expect(pricingStatusLabel("negotiated_offline")).toBe("negotiated_offline");
  });
});

describe("what a price with no amount renders as", () => {
  const pounds = (micros: number) => `£${(micros / 1_000_000).toFixed(2)}`;

  it("renders a settled price as the figure it is", () => {
    expect(customerPriceAmount(knownPrice(4_200_000), pounds)).toBe("£4.20");
  });

  // ⚠ #155 §9.2's defect, in one line: `const displayed = amount ?? 0`. All
  // three of these are the same NULL column and only the status tells them
  // apart, so a reader that coalesces tells a tenant they charged nothing.
  it.each([
    ["unknown", unknownPrice()],
    ["waived", waivedPrice()],
    ["not applicable", priceNotApplicable("fixed_task_pricing")],
  ])("renders a %s price as an absence, never as an amount", (_state, price) => {
    const rendered = customerPriceAmount(price, pounds);

    expect(rendered).not.toBe("£0.00");
    expect(rendered).not.toMatch(CURRENCY);
    expect(rendered).toBe("—");
  });

  // THE STATUS DECIDES, NOT THE AMOUNT, and this is the case that separates the
  // two rules. A branch on `billed_cost_micros === null` is right for every row
  // the database admits today and wrong the moment a zero arrives beside a
  // status that is not `known` — which is a row a wire payload can carry
  // whatever the column constraint says, since the console is downstream of it.
  it("reads the STATUS, so a zero beside a waived price is still an absence", () => {
    const zeroed = { billed_cost_micros: 0, pricing_status: "waived" } as const;

    expect(customerPriceAmount(zeroed, pounds)).toBe("—");
  });
});

describe("what settled, and what every derived number must ask", () => {
  it("gives back the amount when the price settled", () => {
    expect(settledPriceMicros(knownPrice(4_200_000))).toBe(4_200_000);
  });

  it.each([
    ["unknown", unknownPrice()],
    ["waived", waivedPrice()],
    ["not applicable", priceNotApplicable("tenant_not_billing")],
  ])("gives back nothing for a %s price", (_state, price) => {
    expect(settledPriceMicros(price)).toBeNull();
  });

  // ⚠ THE DEFECT THIS FUNCTION EXISTS TO END, and it is not the displayed
  // amount — that one is easy to see and easy to guard. It is the number
  // DERIVED from the amount. The event receipt renders `billed − provider
  // cost`, so a page that guarded the price with the status and computed the
  // margin off the raw column would show a dash in one row and a real signed
  // figure in the next, derived from the very zero the dash denies.
  it("stops a margin being computed from an amount that never settled", () => {
    const waivedAtZero = {
      billed_cost_micros: 0,
      pricing_status: "waived",
    } as const;
    const providerCost = 1_400_000;

    const settled = settledPriceMicros(waivedAtZero);
    expect(settled).toBeNull();

    // What the raw column would have produced, spelled out so the failure names
    // the wrong answer rather than merely missing the right one.
    expect(waivedAtZero.billed_cost_micros - providerCost).toBe(-1_400_000);
  });

  // A `known` status with no amount is a row nothing should produce, and the
  // console is downstream of whatever does. It renders as an absence rather
  // than throwing or coalescing.
  it("gives back nothing when a settled status carries no amount", () => {
    expect(settledPriceMicros({ pricing_status: "known" })).toBeNull();
  });
});

describe("what the console says about a price it does not have", () => {
  it("has a sentence for every status the registry declares", () => {
    for (const status of PRICING_STATUS_VALUES) {
      expect(PRICING_STATUS_EXPLANATIONS[status].trim()).not.toBe("");
    }
  });

  // The reason is read ONLY under `not_applicable`, so the sentence the reader
  // gets there is the reason's rather than the status's — that is what makes
  // "look at the Task's charge" and "there is nothing to look at" two visibly
  // different answers rather than one shared shrug.
  it("prefers the REASON's sentence when a price does not apply", () => {
    for (const reason of NOT_APPLICABLE_REASON_VALUES) {
      expect(customerPriceExplanation(priceNotApplicable(reason))).toBe(
        NOT_APPLICABLE_REASON_EXPLANATIONS[reason],
      );
    }
  });

  it("falls back to the status's own sentence when no reason was sent", () => {
    // Legal on the wire: `not_applicable_reason` is nullable, and the console
    // is downstream of whatever produced it.
    const unexplained = {
      billed_cost_micros: null,
      pricing_status: "not_applicable",
      not_applicable_reason: null,
    } as const;

    expect(customerPriceExplanation(unexplained)).toBe(
      PRICING_STATUS_EXPLANATIONS.not_applicable,
    );
  });

  it("gives the other three statuses their own sentence", () => {
    expect(customerPriceExplanation(knownPrice(1))).toBe(
      PRICING_STATUS_EXPLANATIONS.known,
    );
    expect(customerPriceExplanation(unknownPrice())).toBe(
      PRICING_STATUS_EXPLANATIONS.unknown,
    );
    expect(customerPriceExplanation(waivedPrice())).toBe(
      PRICING_STATUS_EXPLANATIONS.waived,
    );
  });

  // Only `unknown` is missing information; the other two absences are answers.
  // A console that counted `waived` as missing would report a decided loss as
  // an outstanding question, and one that counted `not_applicable` would report
  // a metering-only tenant as owing itself revenue.
  it("names UNKNOWN as the one absence a completeness count is about", () => {
    expect(PRICING_STATUS_EXPLANATIONS.unknown).toMatch(/missing|not yet|has not/i);
    expect(PRICING_STATUS_EXPLANATIONS.waived).toMatch(/decid|waiv|pursue/i);
  });
});
