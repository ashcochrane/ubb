// The words a supplied revenue figure is read under (#508; slice 7 §5).
//
// ⚠ **THE SENTENCE IS TESTED HERE BECAUSE TWO FEATURES RENDER IT.** A chart
// summing supplied amounts owes the view it was drawn under — the customer's
// margin trend and the billing revenue window both do — and a rule two
// surfaces obey belongs in one place with one set of cases, rather than in two
// component tests that could drift into asserting two different sentences.

import { describe, expect, it } from "vitest";

import { REVENUE_BASIS_VALUES } from "@/lib/vocabulary";

import {
  RECOGNITION_METHOD_MEANS,
  recognitionMethodLabel,
  REVENUE_BASIS_MEANS,
  revenueBasisLabel,
  revenueBasisNote,
  spreadsAcrossItsSpan,
} from "./supplied-revenue";

describe("revenueBasisNote", () => {
  // ⚠ **BOTH SENTENCES SAY WHETHER ANYTHING WAS DIVIDED, because that is the
  // whole difference and the thing §5 refuses to leave unsaid.** A tenant
  // reading a day's revenue has to be able to tell a figure earned that day
  // from a slice of one earned across a quarter.
  it("says of each view whether it divides anything", () => {
    // ⚠ CAPITALISED, because the meaning is TWO sentences. An earlier draft
    // lowercased the whole string and put a lower-case letter after a full
    // stop — and these very assertions pinned the defect in place.
    expect(revenueBasisNote("recorded")).toContain("Nothing is divided");
    expect(revenueBasisNote("recognised")).toContain("spread across the period");
    // The join is lower-cased at the seam and nowhere else.
    expect(revenueBasisNote("recorded")).toContain("— each figure whole");
  });

  it("names the view the catalogue's own word for it", () => {
    for (const basis of REVENUE_BASIS_VALUES) {
      expect(revenueBasisNote(basis).toLowerCase()).toContain(
        revenueBasisLabel(basis).toLowerCase(),
      );
    }
  });

  // The branch that should never run, because the concept is closed. It must
  // still not invent English for a token UBB never authored — it says what it
  // was told and no more.
  it("states an unrecognised basis as the token, inventing no meaning", () => {
    const note = revenueBasisNote("smoothed_somehow");
    expect(note).toContain("smoothed_somehow");
    expect(note).not.toContain("divided");
    expect(note).not.toContain("spread");
  });
});

describe("the two concepts' own words", () => {
  it("words every value of each closed set", () => {
    for (const basis of REVENUE_BASIS_VALUES) {
      expect(REVENUE_BASIS_MEANS[basis]).toBeTruthy();
      expect(revenueBasisLabel(basis)).not.toBe(basis);
    }
  });

  // ⚠ THE METHOD DECIDES WHETHER THE TWO VIEWS DIFFER FOR A ROW, so the map
  // and the sentences have to agree: a method described as landing an amount
  // whole must not be one the code spreads.
  it("has each method's sentence agree with whether it spreads", () => {
    expect(spreadsAcrossItsSpan("straight_line")).toBe(true);
    expect(RECOGNITION_METHOD_MEANS.straight_line).toContain("Divided");
    expect(spreadsAcrossItsSpan("on_receipt")).toBe(false);
    expect(RECOGNITION_METHOD_MEANS.on_receipt).toContain("whole");
    expect(recognitionMethodLabel("on_receipt")).toBe("On receipt");
  });

  // A method this build has never met spreads nothing rather than guessing,
  // because guessing would be the console deciding to divide a tenant's figure.
  it("spreads nothing for a method it does not recognise", () => {
    expect(spreadsAcrossItsSpan("declining_balance")).toBe(false);
  });
});
