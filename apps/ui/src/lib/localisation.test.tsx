// Strict label lookup, exercised the way the console actually reaches it (#210).
//
// `tests/contracts/test_label_catalogue.py` is G6: it compares the registry
// against `src/locales/*.json` in both directions and holds the legacy adapter
// to the migration ledger. It reads two files. It cannot run the lookup, so it
// cannot see a catalogue that is complete and unreachable — a broken import, a
// resolver that consults the wrong locale, a fallback quietly reintroduced.
//
// That is this file's subject, and the two are deliberately not the same
// question. Nothing below re-derives G6's coverage rule from the same data it
// checks; every assertion here goes through `resolveLabel`, and the rendering
// cases go through the DOM.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ABSENT_LABEL,
  labelMap,
  missingLabel,
  resolveLabel,
} from "./localisation";
import { catalogue, DEFAULT_LOCALE, LOCALES } from "@/locales";
import * as vocabulary from "./vocabulary";
import { TASK_STATUS_LABEL_KEYS } from "./vocabulary";

/** Every `<CONCEPT>_LABEL_KEYS` export the registry generated. */
const labelKeyMaps = (Object.entries(vocabulary) as [string, unknown][]).filter(
  (entry): entry is [string, Record<string, string>] =>
    entry[0].endsWith("_LABEL_KEYS"),
);

/** A value no registry concept declares, standing in for one UBB has not met. */
const UNFAMILIAR = "quantum_settled";

describe("the label catalogue", () => {
  // Vacuity guard. Two of the loops below are over these collections, and a
  // loop over an empty one passes while proving nothing.
  it("ships a catalogue with wording, for concepts the registry declares", () => {
    expect(labelKeyMaps.length).toBeGreaterThan(20);
    expect(Object.keys(catalogue).length).toBeGreaterThan(100);
    expect(Object.keys(LOCALES)).toContain(DEFAULT_LOCALE);
  });

  it("resolves every generated label key to real words", () => {
    // The rendering-path half of ADR-0008 §4's first promise. G6 proves the
    // JSON covers the registry; this proves the console can reach the words
    // for every value it holds — through the function call sites use.
    for (const [name, keys] of labelKeyMaps) {
      for (const value of Object.keys(keys)) {
        const resolved = resolveLabel(keys, value);
        expect(resolved.kind, `${name}: ${value}`).toBe("labelled");
        expect(resolved.text.trim(), `${name}: ${value}`).not.toBe("");
      }
    }
  });
});

describe("strict lookup", () => {
  it("returns the catalogue's wording for a declared value", () => {
    const resolved = resolveLabel(TASK_STATUS_LABEL_KEYS, "expired");
    expect(resolved).toEqual({
      kind: "labelled",
      key: "task_status.expired",
      text: "Expired",
    });
  });

  it("renders an explicit development error for a value with no wording", () => {
    // The case ADR-0008 §4.3 replaced the humanising fallback with. G6 makes it
    // unreachable for a declared value, which is exactly why the negative form
    // has to be exercised with a synthetic map: a key the catalogue does not
    // carry cannot be conjured out of the shipped vocabulary.
    const orphan = { ghost: "task_status.ghost" };
    const resolved = resolveLabel(orphan, "ghost");

    expect(resolved.kind).toBe("unlabelled");
    expect(resolved.text).toBe("[no label: task_status.ghost]");
    expect(resolved.text).toBe(missingLabel("task_status.ghost"));
    // The point of the marker: it is not, and cannot be mistaken for, copy.
    expect(resolved.text).not.toBe("Ghost");
  });

  it("renders an unfamiliar open value verbatim, never title-cased", () => {
    // ADR-0003 keeps an unseen value legal; ADR-0008 §4.4 decides what it looks
    // like. The second assertion is the one that matters — "Quantum settled" is
    // what the retired `humanize` produced, and it is the shape of invented
    // copy this whole layer exists to abolish.
    const resolved = resolveLabel(TASK_STATUS_LABEL_KEYS, UNFAMILIAR);

    expect(resolved).toEqual({
      kind: "unfamiliar",
      value: UNFAMILIAR,
      text: UNFAMILIAR,
    });
    expect(resolved.text).not.toBe("Quantum settled");
  });

  it("renders an absent value as an absence, not as a name", () => {
    for (const empty of [null, undefined, ""]) {
      const resolved = resolveLabel(TASK_STATUS_LABEL_KEYS, empty);
      expect(resolved.kind).toBe("absent");
      expect(resolved.text).toBe(ABSENT_LABEL);
    }
  });

  it("binds a concept once and keeps the legacy call shape", () => {
    // What makes migrating a vocabulary one line rather than one edit per call
    // site: `labelMap(...)` is called exactly as the retired maps were.
    const taskStatusLabel = labelMap(TASK_STATUS_LABEL_KEYS);

    expect(taskStatusLabel("cancelled")).toBe("Cancelled");
    expect(taskStatusLabel(null)).toBe(ABSENT_LABEL);
    expect(taskStatusLabel(UNFAMILIAR)).toBe(UNFAMILIAR);
  });
});

describe("rendering", () => {
  // #155 §9.2 asks any change touching an economic state for a rendering
  // assertion, on the grounds that "unknown must never render as £0.00". The
  // same argument applies one level up: unknown must never render as a name
  // UBB did not choose, and only the DOM can show what a reader actually sees.
  function Status({ value }: { value: string | null }) {
    return <span data-testid="status">{labelMap(TASK_STATUS_LABEL_KEYS)(value)}</span>;
  }

  it("puts the catalogue's words on the page for a declared value", () => {
    render(<Status value="killed" />);
    expect(screen.getByTestId("status")).toHaveTextContent("Killed");
  });

  it("puts the raw token on the page for an unfamiliar one", () => {
    render(<Status value={UNFAMILIAR} />);

    const rendered = screen.getByTestId("status");
    expect(rendered).toHaveTextContent(UNFAMILIAR);
    expect(rendered.textContent).not.toBe("Quantum settled");
  });

  it("puts an em dash on the page for an absent one", () => {
    render(<Status value={null} />);
    expect(screen.getByTestId("status")).toHaveTextContent(ABSENT_LABEL);
  });
});

// Deliberately NOT here: the legacy adapter's confinement to allowlisted sites.
// The console cannot check its own allowlist — the allowlist is
// `gates/migration-ledger.yaml`, and the check that holds the two together is
// `tests/contracts/test_label_catalogue.py`, where the ledger already lives. A
// vitest copy of it would be the second encoding ADR-0006 §4 warns about.
