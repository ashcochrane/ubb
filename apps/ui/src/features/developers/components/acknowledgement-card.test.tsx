// One recorded response's card, for the states a Verify run's fixtures do not
// all reach (#371, #581).
//
// The platform-written Verify answers (`api/verifications/`) are rendered
// through this card by the page's own tests. The states proved HERE are the
// ones those answers cannot produce, so the card is rendered DIRECTLY with a
// response this file assembles — the same reasoning as
// `features/events/components/event-receipt-price.test.tsx`: a rendering test
// cannot see a narrowing defect where the mock returns its own fixture object.
//
// ⚠ WHY THIS SURFACE OWES THE ASSERTION SEPARATELY FROM THE RECEIPT. This card
// is what an integrator reads to learn what UBB recorded, and it is a compact
// stat grid rather than a detail list — the status goes IN the amount's cell
// where there is no amount. #330 made the supplier cost do exactly that and
// left the customer price falling back to a bare dash; three of the four price
// statuses null that column and they do not mean the same thing, so the dash
// was the ambiguity the cost half had already fixed.

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UNRECOGNISED_MARK } from "@/components/shared/open-set-value";
import {
  notApplicableReasonLabel,
  pricingStatusLabel,
  pricingStatusReasonLabel,
} from "@/lib/customer-price";
import {
  ceilingStop,
  completeTotal,
  endedWorkStop,
  hardFloorStop,
  incompletePriceTotal,
  incompleteTotal,
  knownCost,
  knownPrice,
  negativePriceUnsupported,
  poolStop,
  priceNotApplicable,
  unknownCost,
  unknownPrice,
  waivedPrice,
  type CustomerPriceScenario,
  type StopScenario,
} from "@/lib/economic-scenarios";
import { ABSENT_LABEL, labelMap } from "@/lib/localisation";
import { costingStatusLabel } from "@/lib/supplier-cost";
import { UNKNOWN_TOTAL } from "@/lib/total-reading";
import {
  REASON_CODE_KNOWN_VALUES,
  TRIGGER_SOURCE_KNOWN_VALUES,
  TRIGGER_SOURCE_LABEL_KEYS,
} from "@/lib/vocabulary";

/** The catalogue's word for a mechanism, read through the console's own lookup. */
const triggerSourceLabel = labelMap(TRIGGER_SOURCE_LABEL_KEYS);

import { verificationFromText } from "../api/exact-figures";
import type { VerifiedAcknowledgement } from "../api/types";
import { AcknowledgementCard, REPLAY_TASK_TOTALS } from "./acknowledgement-card";

/** A version-2 Pricing Receipt, the only shape the contract publishes (#558). */
const A_RECEIPT: VerifiedAcknowledgement["pricing_receipt"] = {
  receipt_schema_version: 2,
  pricing_engine_version: "3.0.0",
  subject_type: "usage_event",
  subject_id: "b1c2d3e4-5f60-4718-a92b-3c4d5e6f7081",
  effective_at: "2026-07-09T12:14:07Z",
  currency: "usd",
  costing: { method: "calculated", status: "known", detail: {} },
  pricing: { method: "direct_event_price", status: "known",
             detail: { pricing_mode: "event_priced" } },
  totals: { provider_cost_micros: 61_000, billed_cost_micros: 1 },
  provenance: {},
};

/**
 * One recorded response, with its price composed and everything else ordinary.
 *
 * Only the price varies, so a failure below can only be about the price.
 */
function responseWith(price: CustomerPriceScenario): VerifiedAcknowledgement {
  return {
    event_id: "b1c2d3e4-5f60-4718-a92b-3c4d5e6f7081",
    suspended: false,
    grouping_fields: {},
    ...price,
    ...knownCost(61_000),
    new_balance_micros: 4_000_000,
    measurements: { input_tokens: "900" },
    uncosted_measurement_keys: [],
    pricing_receipt: A_RECEIPT,
    stop: false,
    stop_reason: null,
    stop_scope: null,
    stop_context: null,
    trigger_source: null,
    stop_bound_micros: null,
    stop_measured_micros: null,
    task_id: null,
    parent_task_id: null,
  };
}

function renderCard(response: VerifiedAcknowledgement, replay = false) {
  render(
    <AcknowledgementCard title="Acknowledgement" response={response} currency="usd" replay={replay} />,
  );
}

function stat(label: string): string {
  const cell = screen.getByText(label).closest("div");
  expect(cell).not.toBeNull();
  return cell?.textContent ?? "";
}

const priceStat = () => stat("Billed cost");

describe("AcknowledgementCard — the customer price", () => {
  it("renders a settled price as the figure it is", () => {
    renderCard(responseWith(knownPrice(187_500)));

    expect(priceStat()).toContain("$0.1875");
  });

  // A real, resolved zero stays readable as one — the case the supplier half's
  // test already protects, asserted here so naming the absences cannot take it
  // away. `known` at zero means UBB priced this event at nothing on purpose.
  it("keeps a resolved zero as a zero", () => {
    renderCard(responseWith(knownPrice(0)));

    expect(priceStat()).toContain("$0.00");
  });

  // ⚠ THE ASSERTION THIS FILE EXISTS FOR. All three null the same column, and
  // a bare dash — what shipped before #371 — cannot tell them apart.
  it.each([
    ["unknown", unknownPrice()],
    ["waived", waivedPrice()],
    ["not_applicable", priceNotApplicable("fixed_task_pricing")],
  ] as const)("names a %s price in the cell, never zeroes it", (status, price) => {
    renderCard(responseWith(price));

    expect(priceStat()).toContain(pricingStatusLabel(status));
    expect(priceStat()).not.toContain("$0.00");
    expect(priceStat()).not.toMatch(/[$£€]\s*-?[\d,]/);
  });

  it("names the cause where the status has one", () => {
    renderCard(responseWith(priceNotApplicable("fixed_task_pricing")));

    expect(screen.getByText("Why")).toBeInTheDocument();
    expect(screen.getByText(notApplicableReasonLabel("fixed_task_pricing"))).toBeInTheDocument();
  });

  it("asks WHY only where the status has a cause to give", () => {
    renderCard(responseWith(waivedPrice()));

    expect(screen.queryByText("Why")).not.toBeInTheDocument();
  });

  // ⚠ #603 A2: a negative calculated price arrives `unknown` WITH ITS REASON,
  // and the card says both — in the status and in the cell — never the
  // calculated number and never a zero. A plain `unknown` says no reason.
  it("names an unknown price's reason beside its status, and states no amount", () => {
    renderCard(responseWith(negativePriceUnsupported()));

    const said = `${pricingStatusLabel("unknown")} · ${pricingStatusReasonLabel("negative_price_unsupported")}`;
    expect(stat("Price status")).toContain(said);
    expect(priceStat()).toContain(said);
    expect(priceStat()).not.toMatch(/[$£€]\s*-?[\d,]/);
  });

  it("names no reason beside an unknown price that carries none", () => {
    renderCard(responseWith(unknownPrice()));

    expect(stat("Price status")).not.toContain(pricingStatusReasonLabel("negative_price_unsupported"));
  });
});

describe("AcknowledgementCard — statuses as given", () => {
  // #473's confident price over an unresolved cost is the response's to fix,
  // not this card's: both statuses are shown as returned, side by side.
  it("shows a known price beside an unresolved cost, as the response states them", () => {
    renderCard({ ...responseWith(knownPrice(187_500)), ...unknownCost("cost_rate_missing") });

    expect(stat("Price status")).toContain(pricingStatusLabel("known"));
    expect(stat("Costing status")).toContain(costingStatusLabel("unresolved"));
    expect(stat("Provider cost")).toContain(costingStatusLabel("unresolved"));
    expect(stat("Provider cost")).not.toMatch(/[$£€]\s*-?[\d,]/);
    expect(priceStat()).toContain("$0.1875");
  });
});

describe("AcknowledgementCard — the task totals", () => {
  it("says a replay's null totals are expected rather than missing", () => {
    renderCard(responseWith(knownPrice(187_500)), true);
    expect(stat("Task totals")).toContain(REPLAY_TASK_TOTALS);
  });

  it("says nothing about totals a first acknowledgement does not carry", () => {
    renderCard(responseWith(knownPrice(187_500)));
    expect(screen.queryByText("Task totals")).toBeNull();
  });

  // #537: a total whose parts were all left out is NO figure. The fixture is
  // composed, so the zero and the count that qualifies it travel together.
  it("never renders a total of nothing known as a zero amount", () => {
    const cost = incompleteTotal(0, 1);
    const price = incompletePriceTotal(0, 1);
    renderCard({
      ...responseWith(unknownPrice()),
      ...unknownCost("cost_rate_missing"),
      task_total_provider_cost_micros: cost.micros,
      task_total_unresolved_event_count: cost.unresolved_event_count,
      task_total_billed_cost_micros: price.micros,
      task_total_unpriced_event_count: price.unpriced_event_count,
    });

    for (const label of ["Task provider cost so far", "Task billed so far"]) {
      expect(stat(label)).toContain(UNKNOWN_TOTAL);
      expect(stat(label)).not.toContain("$0.00");
    }
  });

  // At an event's precision: the cent-rounded total every other surface uses
  // would write this known amount as `$0.00`.
  it("renders a whole total as its figure, at an event's precision", () => {
    const cost = completeTotal(314);
    renderCard({
      ...responseWith(knownPrice(471)),
      task_total_provider_cost_micros: cost.micros,
      task_total_unresolved_event_count: cost.unresolved_event_count,
    });

    expect(stat("Task provider cost so far")).toMatch(/\$0\.0003$/);
  });

  // A total without the count of what it left out cannot say whether it is
  // whole, so it is not shown — never read as whole by defaulting the count.
  it("shows no total whose count is missing", () => {
    renderCard({
      ...responseWith(knownPrice(471)),
      task_total_provider_cost_micros: 314,
      task_total_unresolved_event_count: null,
    });

    expect(screen.queryByText("Task provider cost so far")).toBeNull();
    expect(screen.queryByText("Task totals")).toBeNull();
  });
});

describe("AcknowledgementCard — the Pricing Receipt", () => {
  it("carries the receipt as returned", () => {
    renderCard({ ...responseWith(knownPrice(1)), pricing_receipt: A_RECEIPT });

    expect(screen.getByText("Pricing Receipt")).toBeInTheDocument();
    expect(document.body.textContent).toContain('"receipt_schema_version": 2');
  });
});

/** A stop word no registry entry names — a control UBB has not met, or not yet. */
const UNRECOGNISED_STOP = "a_stop_from_next_year";

function stopped(reason: string): VerifiedAcknowledgement {
  return { ...responseWith(knownPrice(187_500)), stop: true, stop_reason: reason, stop_scope: "task" };
}

function reasonStat(): HTMLElement {
  const cell = screen.getByText("Reason").closest("div");
  if (!cell) throw new Error("no Reason stat");
  return cell;
}

// The stop verdict's word renders through the console's one open-set helper
// (#466; slice 6 §18; Testing Decisions claim 15). A Verify run only ever
// answers a registry word, so the unfamiliar branch is assembled here.
describe("AcknowledgementCard — the stop verdict's word", () => {
  it("renders a value the registry knows in the catalogue's words, unmarked", () => {
    expect(REASON_CODE_KNOWN_VALUES.length).toBeGreaterThan(0);
    const known = REASON_CODE_KNOWN_VALUES[0];
    renderCard(stopped(known));

    const rendered = reasonStat().querySelector("[data-label]");
    expect(rendered).toHaveAttribute("data-label", "labelled");
    expect(rendered?.textContent?.trim()).not.toBe("");
    expect(rendered?.textContent).not.toBe(known);
    expect(reasonStat()).not.toHaveTextContent(UNRECOGNISED_MARK);
  });

  it("renders a value the registry has never seen as the token, marked, never humanised", () => {
    renderCard(stopped(UNRECOGNISED_STOP));

    const rendered = reasonStat().querySelector("[data-label]");
    expect(rendered).toHaveAttribute("data-label", "unfamiliar");
    expect(reasonStat()).toHaveTextContent(UNRECOGNISED_STOP);
    expect(reasonStat()).toHaveTextContent(UNRECOGNISED_MARK);
    expect(reasonStat()).not.toHaveTextContent("A stop from next year");
  });
});

/** A mechanism no registry entry names, as a later platform could send one. */
const UNRECOGNISED_MECHANISM = "a_mechanism_from_next_year";

/** One recorded response that is a stop, composed from one row of ADR-0019's
 * table: only the stop varies. */
function stoppedBy(stop: StopScenario): VerifiedAcknowledgement {
  return { ...responseWith(knownPrice(187_500)), ...stop };
}

/** The Stop verdict block, so a figure elsewhere on the card is never found. */
function verdict(): HTMLElement {
  const block = screen.getByText("Stop verdict").closest("div.space-y-2");
  if (!(block instanceof HTMLElement)) throw new Error("no Stop verdict block");
  return block;
}

function verdictStat(label: string): HTMLElement {
  const cell = within(verdict()).getByText(label).closest("div");
  if (!cell) throw new Error(`no ${label} stat in the Stop verdict`);
  return cell;
}

/** What a Stop verdict stat shows as its value, exactly. */
function shown(label: string): string | undefined {
  return verdictStat(label).querySelector("dd")?.textContent ?? undefined;
}

/** Any amount of money written as a figure, a zero among them. */
const A_FIGURE = /[$£€]\s*-?[\d,]|^\s*-?0\s*$/;

// #569 published how a stop was applied and what it was measured on, and the
// card renders exactly what the acknowledgement carries (#585): nothing is
// computed, estimated, defaulted or filled. The platform-written Verify
// answers are never stops (the run's tenant enforces nothing), so every state
// here is composed (`@/lib/economic-scenarios`), on a response this file
// assembles.
describe("AcknowledgementCard — how the stop was applied (#585)", () => {
  it("names the mechanism a value the registry knows in the catalogue's words", () => {
    expect(TRIGGER_SOURCE_KNOWN_VALUES).toContain("enforcement_patrol");
    renderCard(
      stoppedBy(poolStop({ opened_by: "enforcement_patrol", stop_line_micros: 4_000_000n, charges_micros: 4_500_000n })),
    );

    const rendered = verdictStat("Applied by").querySelector("[data-label]");
    expect(rendered).toHaveAttribute("data-label", "labelled");
    expect(rendered?.textContent).toBe(triggerSourceLabel("enforcement_patrol"));
    expect(verdictStat("Applied by")).not.toHaveTextContent(UNRECOGNISED_MARK);
  });

  it("renders a mechanism the registry has never seen as the token, marked, never humanised", () => {
    renderCard(
      stoppedBy(poolStop({ opened_by: UNRECOGNISED_MECHANISM, stop_line_micros: 4_000_000n, charges_micros: 4_500_000n })),
    );

    const rendered = verdictStat("Applied by").querySelector("[data-label]");
    expect(rendered).toHaveAttribute("data-label", "unfamiliar");
    expect(verdictStat("Applied by")).toHaveTextContent(UNRECOGNISED_MECHANISM);
    expect(verdictStat("Applied by")).toHaveTextContent(UNRECOGNISED_MARK);
    expect(verdictStat("Applied by")).not.toHaveTextContent("A mechanism from next year");
  });

  it("renders the bound and the amount measured against it as their figures", () => {
    renderCard(stoppedBy(ceilingStop({ scope: "task", ceiling_micros: 5_000_000n, cost_micros: 6_000_000n })));

    expect(shown("Bound")).toBe("$5.00");
    expect(shown("Measured")).toBe("$6.00");
  });

  // To the micro: a cent-rounded figure would write both as $0.00, and an
  // event's four places would round the amount.
  it("renders a small bound and amount to the micro", () => {
    renderCard(stoppedBy(ceilingStop({ scope: "subtask", ceiling_micros: 300n, cost_micros: 471n })));

    expect(shown("Bound")).toBe("$0.0003");
    expect(shown("Measured")).toBe("$0.000471");
  });

  // ⚠ The two are read against each other. A balance one micro under its
  // floor is what stopped the work; rounded to a cent, the two would read as
  // one amount.
  it("never renders a bound and the amount measured against it as one when they differ", () => {
    renderCard(
      stoppedBy(hardFloorStop({ opened_by: "usage_ingest", min_balance_micros: 1_000_000n, balance_micros: -1_000_001n })),
    );

    expect(shown("Bound")).toBe("-$1.00");
    expect(shown("Measured")).toBe("-$1.000001");
  });

  // ⚠ A hard floor's figures are negative: the floor as a balance, and the
  // balance below it. The sign is the fact.
  it("renders a hard floor's negative figures as negative", () => {
    renderCard(
      stoppedBy(hardFloorStop({ opened_by: "usage_ingest", min_balance_micros: 1_000_000n, balance_micros: -1_500_000n })),
    );

    expect(shown("Bound")).toBe("-$1.00");
    expect(shown("Measured")).toBe("-$1.50");
  });

  // A zero floor is a real bound: it renders as the zero it is.
  it("renders a zero floor as a zero, beside the balance below it", () => {
    renderCard(stoppedBy(hardFloorStop({ opened_by: "usage_ingest", min_balance_micros: 0n, balance_micros: -400n })));

    expect(shown("Bound")).toBe("$0.00");
    expect(shown("Measured")).toBe("-$0.0004");
  });

  // ⚠ The figures run to the platform's signed 64-bit money column, past what
  // a number holds (2^53), and `JSON.parse` would round them before this card
  // saw them. So a Verify answer is read off its TEXT — by the one function
  // the API client and the mock both read it with — and every digit reaches
  // the card. The answer here is text, as the platform sends it.
  it.each([
    ["a hard floor at the most negative amounts a money column holds", "hard_floor", "customer",
      "-9223372036854775807", "-9223372036854775808",
      "-$9,223,372,036,854.775807", "-$9,223,372,036,854.775808"],
    ["a ceiling past 2^53, crossed at the largest", "task_cogs_ceiling", "task",
      "9007199254740993", "9223372036854775807",
      "$9,007,199,254.740993", "$9,223,372,036,854.775807"],
  ] as const)("renders %s to its last digit, read off the answer's text", (_what, reason, scope, bound, measured, boundShown, measuredShown) => {
    const acknowledgement = {
      ...responseWith(knownPrice(187_500)),
      stop: true,
      stop_reason: reason,
      stop_scope: scope,
      trigger_source: "usage_ingest",
      stop_bound_micros: "@bound",
      stop_measured_micros: "@measured",
    };
    const text = JSON.stringify({ records: [{ acknowledgement }] })
      .replace('"@bound"', bound)
      .replace('"@measured"', measured);
    // Not vacuous: the number `JSON.parse` makes of the text has lost digits.
    expect(String(JSON.parse(text).records[0].acknowledgement.stop_measured_micros)).not.toBe(measured);

    const read = verificationFromText(text).records[0]?.acknowledgement;
    expect(read).toBeDefined();
    renderCard(read!);

    expect(shown("Bound")).toBe(boundShown);
    expect(shown("Measured")).toBe(measuredShown);
  });

  // ⚠ THE ASSERTION THIS SECTION EXISTS FOR. Work that had already ended names
  // no bound, no amount and no mechanism: each is NO FIGURE, never 0 and never
  // $0.00.
  it("renders what does not apply as no figure, never as a zero", () => {
    renderCard(stoppedBy(endedWorkStop("task")));

    for (const label of ["Applied by", "Bound", "Measured"]) {
      expect(shown(label), label).toBe(ABSENT_LABEL);
      expect(shown(label) ?? "", label).not.toMatch(A_FIGURE);
    }
  });
});
