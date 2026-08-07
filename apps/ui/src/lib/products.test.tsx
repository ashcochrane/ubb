// The tenant-product surface, exercised the way the console reaches it (#241).
//
// `tests/contracts/test_label_catalogue.py` is G6: it proves the catalogue
// covers the registry and that the legacy adapter no longer words this concept.
// It reads files. It cannot run the lookup, so it cannot see a binding that
// points at the wrong concept, a catalogue the module never reaches, or a
// fallback quietly reintroduced — which is this file's subject.
//
// `localisation.test.tsx` is the prior art and states the general rule over
// `task_status`. What is asserted again here is the half that is specific to
// this concept: that the products the console offers are the registry's three
// and only those, and that a product value UBB has never met renders as the
// token the server sent rather than as English UBB invented for it.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PRODUCT_DESCRIPTIONS, productLabel } from "./products";
import { TENANT_PRODUCT_VALUES } from "./vocabulary";

/** A product value no registry concept declares — one UBB has never met. */
const UNFAMILIAR = "quantum_ledger";

describe("productLabel", () => {
  it("words every declared product from the shipped catalogue", () => {
    // Vacuity guard first: a loop over an empty value list passes while
    // proving nothing, and this list is generated rather than written here.
    expect(TENANT_PRODUCT_VALUES.length).toBe(3);

    for (const product of TENANT_PRODUCT_VALUES) {
      const words = productLabel(product);
      expect(words.trim(), product).not.toBe("");
      // Not the token back: that is what the unfamiliar branch returns, so a
      // binding pointed at the wrong concept's label keys would still produce
      // a non-empty string and pass the assertion above.
      expect(words, product).not.toBe(product);
    }
  });

  it("renders an unfamiliar product verbatim, never title-cased", () => {
    // ADR-0008 §4.3 reverses #154 §9.1 on exactly this map: `productLabel`
    // used to fall back to the humaniser, which turned this input into
    // "Quantum ledger" — user-facing terminology manufactured by a string
    // transformation. ADR-0003 keeps an unseen value legal, so the case is
    // reachable; what changes is what a reader sees.
    render(<span data-testid="product">{productLabel(UNFAMILIAR)}</span>);

    // `textContent`, not `toHaveTextContent`: the latter is a substring match
    // and would pass on "Quantum ledger (quantum_ledger)".
    expect(screen.getByTestId("product").textContent).toBe(UNFAMILIAR);
  });
});

describe("PRODUCT_DESCRIPTIONS", () => {
  it("carries a sentence for exactly the declared products", () => {
    // ADR-0008 §4.5 keeps explanatory prose out of the registry, so this copy
    // is the console's own. `satisfies Record<TenantProduct, string>` makes a
    // MISSING entry a typecheck failure and an extra one an excess property —
    // neither can reach this assertion. What it adds is that the keys are the
    // registry's values rather than a set that merely typechecks against a
    // stale generated type, and that no entry is blank.
    expect(Object.keys(PRODUCT_DESCRIPTIONS).sort()).toEqual(
      [...TENANT_PRODUCT_VALUES].sort(),
    );
    for (const product of TENANT_PRODUCT_VALUES) {
      expect(PRODUCT_DESCRIPTIONS[product].trim(), product).not.toBe("");
    }
  });
});
