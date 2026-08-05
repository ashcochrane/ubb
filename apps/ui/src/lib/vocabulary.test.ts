// The console's own half of the vocabulary gate (issue #207).
//
// `tests/contracts/test_generated_vocabulary.py` proves the committed artifact
// is exactly what `domain-vocabulary/` renders. It cannot prove the artifact is
// USABLE from here: a file that fails to parse, exports nothing, or types its
// label maps so loosely that `satisfies` proves nothing would satisfy a
// byte-comparison perfectly. So this suite asks the question only the console's
// own toolchain can answer — does TypeScript accept it, and does what it
// exports hold together?
//
// It is deliberately GENERIC over the exports rather than a list of concept
// names. Eight slices of renaming are coming; a test that named twenty concepts
// would be edited by every one of them, and the invariants below are what
// actually matter to a consumer. The two named cases at the bottom are the
// exception, because open-versus-closed is a claim about TYPES that only a
// concrete type can make.

import { describe, expect, it } from "vitest";
import * as vocabulary from "./vocabulary";
import {
  REASON_CODE_KNOWN_VALUES,
  TASK_STATUS_VALUES,
  type ReasonCode,
  type TaskStatus,
} from "./vocabulary";

// Widened to `unknown` on purpose. `Object.entries` over the namespace import
// types every value as the union of all seventy-odd exports, which no narrowing
// predicate can be a subtype of — and the whole point here is to inspect the
// exports as data rather than to name them one by one.
const exports_ = Object.entries(vocabulary) as [string, unknown][];

/** Every `<CONCEPT>_VALUES` / `<CONCEPT>_KNOWN_VALUES` export, by name. */
const valueLists = exports_.filter(
  (entry): entry is [string, readonly string[]] =>
    (entry[0].endsWith("_VALUES") || entry[0].endsWith("_KNOWN_VALUES")) &&
    Array.isArray(entry[1]),
);

/** Every `<CONCEPT>_LABEL_KEYS` export, by name. */
const labelMaps = exports_.filter(
  (entry): entry is [string, Record<string, string>] =>
    entry[0].endsWith("_LABEL_KEYS"),
);

/** The value list a label map is keyed on — known values for an open concept. */
function valuesFor(labelMapName: string): readonly string[] {
  const stem = labelMapName.slice(0, -"_LABEL_KEYS".length);
  const found = valueLists.find(
    ([name]) => name === `${stem}_VALUES` || name === `${stem}_KNOWN_VALUES`,
  );
  if (!found) throw new Error(`${labelMapName} has no value list`);
  return found[1];
}

describe("the generated vocabulary module", () => {
  // Vacuity guard. Every assertion below is a loop, and a loop over an empty
  // list passes while proving nothing — which is exactly how a module that
  // failed to export anything would slip through.
  it("exports a value list and a label map for many concepts", () => {
    expect(valueLists.length).toBeGreaterThan(20);
    expect(labelMaps.length).toBe(valueLists.length);
  });

  it("declares no empty or duplicated value set", () => {
    for (const [name, values] of valueLists) {
      expect(values.length, name).toBeGreaterThan(0);
      expect(new Set(values).size, name).toBe(values.length);
    }
  });

  it("labels exactly the values of its concept, no more and no fewer", () => {
    // The `satisfies Record<…, string>` in the artifact makes TypeScript prove
    // the map is TOTAL over its value type. It cannot prove the map has no
    // EXTRA key, because `as const` widens nothing away — so that half is
    // checked here, at runtime, where the object's own keys are visible.
    for (const [name, labels] of labelMaps) {
      expect(Object.keys(labels).sort(), name).toEqual([...valuesFor(name)].sort());
    }
  });

  it("keys every label under one prefix, ending in the value it labels", () => {
    for (const [name, labels] of labelMaps) {
      const prefixes = new Set<string>();
      for (const [value, key] of Object.entries(labels)) {
        expect(key, `${name}.${value}`).toBe(
          `${key.slice(0, key.length - value.length - 1)}.${value}`,
        );
        prefixes.add(key.slice(0, key.length - value.length - 1));
      }
      // One concept, one prefix. Two would mean a label catalogue could not
      // tell which concept a key belongs to (#210's subject).
      expect([...prefixes], name).toHaveLength(1);
    }
  });

  it("carries no user-facing English — tokens and label keys only", () => {
    // ADR-0008 §4: the registry generates the value sets and the stable label
    // KEYS; the English lives in the console's own catalogue. A space is the
    // cheapest reliable tell that a word has arrived where a token belongs.
    for (const [name, values] of valueLists) {
      for (const value of values) {
        expect(value, `${name}: ${value}`).not.toMatch(/\s/);
      }
    }
    for (const [name, labels] of labelMaps) {
      for (const key of Object.values(labels)) {
        expect(key, `${name}: ${key}`).not.toMatch(/\s/);
      }
    }
  });
});

describe("the kind a concept declares reaches the console as a type", () => {
  // These two are the reason the artifact bothers with types at all, and the
  // one claim a generic loop cannot make: a type is not a runtime value, so
  // "an open concept admits an unknown value" is only checkable by writing an
  // assignment TypeScript has to accept, and its closed counterpart by writing
  // one it has to reject.
  it("lets an open concept carry a value UBB has never seen", () => {
    // ADR-0003: the registry learning about a new value is not a breaking
    // change, so the console must render one it has not seen rather than fail.
    const unseen: ReasonCode = "a_reason_ubb_has_not_shipped_yet";

    expect(REASON_CODE_KNOWN_VALUES).not.toContain(unseen);
  });

  it("refuses a value a closed concept does not declare", () => {
    // @ts-expect-error a closed concept is exactly its declared values, and
    // this assignment must not compile. If the registry ever declares
    // "not_a_task_status", THIS LINE turns red — which is the correct alarm.
    const invalid: TaskStatus = "not_a_task_status";

    expect(TASK_STATUS_VALUES).not.toContain(invalid);
  });
});
