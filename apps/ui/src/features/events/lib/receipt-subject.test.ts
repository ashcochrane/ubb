import { describe, expect, it } from "vitest";

import { PRICING_RECEIPT_SUBJECT_TYPE_VALUES } from "@/lib/vocabulary";

import {
  RECEIPT_SUBJECT_EXPLANATIONS,
  pricingReceiptSubjectTypeLabel,
  receiptExplanation,
} from "./receipt-subject";

describe("what a receipt explains", () => {
  it("takes each subject's name from the catalogue, not from the console", () => {
    expect(pricingReceiptSubjectTypeLabel("usage_event")).toBe("Usage event");
    expect(pricingReceiptSubjectTypeLabel("charge")).toBe("Charge");
  });

  it("has a sentence for every subject the registry declares", () => {
    for (const subject of PRICING_RECEIPT_SUBJECT_TYPE_VALUES) {
      expect(RECEIPT_SUBJECT_EXPLANATIONS[subject].trim()).not.toBe("");
    }
    expect(Object.keys(RECEIPT_SUBJECT_EXPLANATIONS).sort()).toEqual(
      [...PRICING_RECEIPT_SUBJECT_TYPE_VALUES].sort(),
    );
  });

  // The two subjects are two different records — one derived an amount from
  // measured quantities and a rule, the other carries a price agreed before
  // any work ran — and a reader has to be told which they are looking at
  // before the record is shown, or a charge's empty detail reads as a gap.
  it("gives the two subjects two different sentences", () => {
    expect(RECEIPT_SUBJECT_EXPLANATIONS.charge).not.toBe(
      RECEIPT_SUBJECT_EXPLANATIONS.usage_event,
    );
    expect(RECEIPT_SUBJECT_EXPLANATIONS.charge).toMatch(/one agreed price/);
    expect(RECEIPT_SUBJECT_EXPLANATIONS.charge).toMatch(/nothing is missing/);
  });

  // The receipt is not evidence a customer was charged, and the sentence that
  // says so must survive the second subject arriving: it is the one every
  // receipt opened with before there were two.
  it("keeps the not-evidence-of-a-charge sentence on the ordinary receipt", () => {
    expect(RECEIPT_SUBJECT_EXPLANATIONS.usage_event).toMatch(
      /not evidence that a customer was charged/,
    );
  });

  // Nullable on the wire, and a value the registry has never seen is legal
  // there too. Neither is a Charge, so neither gets the charge's sentence —
  // which would tell a reader the price was agreed for a posting nobody
  // agreed anything about.
  it("reads a stated, an unstated and an unfamiliar subject as the ordinary case", () => {
    expect(receiptExplanation("charge")).toBe(RECEIPT_SUBJECT_EXPLANATIONS.charge);
    expect(receiptExplanation("usage_event")).toBe(
      RECEIPT_SUBJECT_EXPLANATIONS.usage_event,
    );
    expect(receiptExplanation(null)).toBe(RECEIPT_SUBJECT_EXPLANATIONS.usage_event);
    expect(receiptExplanation(undefined)).toBe(
      RECEIPT_SUBJECT_EXPLANATIONS.usage_event,
    );
    expect(receiptExplanation("some_future_subject")).toBe(
      RECEIPT_SUBJECT_EXPLANATIONS.usage_event,
    );
  });
});
