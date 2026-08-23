// What a rule's two vocabularies are called, and which slots it may pin.
//
// Identity is the registry's (`@/lib/vocabulary`), expression the catalogue's
// (`@/locales`, reached through `@/lib/localisation`) — the split
// `@/lib/products`, `@/lib/customer-price` and `features/events/lib/measurements`
// all make.
//
// THIS LIVES IN THE PRICING FEATURE rather than in `lib/` because this
// feature's screens are the only readers. `@/lib/customer-price` states the
// opposite rule for itself and the two agree: that one is read by two features
// that cannot share one, these by tables and dialogs a few files away.
//
// ⚠ **THE TWO CONCEPTS ARE A NEAR MISS AND THE COMMENTS ARE THE GUARD RAIL.**
// "Structure" means the mathematical shape and nothing else (ADR-0006 §3) — an
// amount per unit, or a component that applies once. "Method" says how the
// price was DERIVED — a margin over what the call cost, or an amount attached
// to the event. A reader reaching for "the pricing model" lands on whichever
// they saw last, and a rule may move either without the other.

import { formatMicros, formatPrice } from "@/lib/format";
import { labelMap } from "@/lib/localisation";
import { RATE_STRUCTURE_LABEL_KEYS } from "@/lib/vocabulary";
import type { BookChangeIn, GroupingFieldDef, Rule } from "../api/types";

/**
 * The catalogue's name for a rule's arithmetic shape.
 *
 * ⚠ **AND `pricingMethodLabel` IS NOT HERE, WHICH IS THE SAME RULE ANSWERING
 * DIFFERENTLY.** This one has a single reader — the rules table and the diff
 * beside it, both in this feature — so it lives in the feature. The method is
 * rendered by the events feature's receipt as well, and the console's imports
 * only flow down, so its binding sits in `@/lib/customer-price` where both can
 * reach it. Two features reading one concept is what decides a `lib/` home;
 * "these two words look similar" is not.
 */
export const rateStructureLabel = labelMap(RATE_STRUCTURE_LABEL_KEYS);

/**
 * The four selectors every rule has by name, in the order the ladder reads
 * them.
 *
 * Named separately from the grouping slots because they ARE separate: these
 * are columns UBB defines, and the ten below are the tenant's own vocabulary.
 * A list that ran the two together would be a screen asking a tenant to
 * declare `provider`.
 */
export const NAMED_SELECTORS = [
  { name: "provider", label: "Provider" },
  { name: "event_type", label: "Event type" },
  { name: "task_type", label: "Task type" },
  { name: "subtask_type", label: "Subtask type" },
] as const;

export type NamedSelector = (typeof NAMED_SELECTORS)[number]["name"];

/**
 * One pinned selector, ready to render: the word a tenant chose, and the value.
 *
 * ⚠ **THE SLOT NUMBER NEVER REACHES A SCREEN**, which is #277's ruling applied
 * one feature over. The event receipt used to show three rows reading
 * "Dimension 1..3" — console English for a slot number the tenant never chose,
 * and only ever three of the ten that exist. A rule's row is keyed by the same
 * slots, so it inherits the same defect unless the registry is read back.
 */
export interface PinnedSelector {
  readonly key: string;
  readonly value: string;
}

/**
 * Which grouping fields a rule pins, labelled with the tenant's own key.
 *
 * ⚠ **DRIVEN OFF THE TENANT'S REGISTRY, WHICH IS WHY IT TAKES ONE.** The
 * alternative — walking `grouping_field_1..10` off the rule and printing the
 * slot — is what ruling 15's six-of-ten gap looked like from the console side:
 * a hand-written list that is right until the count changes. A tenant that has
 * declared four fields sees four; one that has declared ten sees ten; and a
 * rule pinned on a slot the tenant has since retired still renders, because
 * the pin is on the rule rather than on the declaration.
 */
export function pinnedGroupingFields(
  rule: Rule,
  declared: readonly GroupingFieldDef[],
): PinnedSelector[] {
  const pins: PinnedSelector[] = [];
  for (const field of declared) {
    const value = rule[field.slot as keyof Rule];
    if (typeof value === "string" && value !== "") {
      pins.push({ key: field.key, value });
    }
  }
  return pins;
}

/** Every selector a rule pins, named and declared alike — or none at all. */
export function pinnedSelectors(
  rule: Rule,
  declared: readonly GroupingFieldDef[],
): PinnedSelector[] {
  const named = NAMED_SELECTORS.flatMap(({ name, label }) => {
    const value = rule[name];
    return value === "" ? [] : [{ key: label.toLowerCase(), value }];
  });
  return [...named, ...pinnedGroupingFields(rule, declared)];
}

/**
 * The slots a rule may be pinned on, in declaration order.
 *
 * Retired declarations are left out of what the EDITOR offers while a rule
 * that already pins one still renders it: a tenant who has stopped using a
 * grouping field should not be able to write new rules against it, and must
 * still be able to read the rules they wrote when they did.
 */
export function pinnableGroupingFields(
  declared: readonly GroupingFieldDef[],
): GroupingFieldDef[] {
  return declared.filter((field) => !field.retired);
}

/**
 * The selectors one diff row pins, named the way the rules table names them.
 *
 * The diff and the table describe the same rule and had two hand-written lists
 * of the four named selectors between them, which disagreed on the wording — so
 * one screen said `event=` and the other `event type=` about the same column. A
 * diff row carries its grouping fields already keyed by the tenant's own key,
 * which is why this needs no registry where `pinnedSelectors` does.
 */
export function pinnedInDiff(row: {
  provider: string;
  event_type: string;
  task_type: string;
  subtask_type: string;
  grouping_fields?: Readonly<Record<string, string>> | undefined;
}): PinnedSelector[] {
  const named = NAMED_SELECTORS.flatMap(({ name, label }) => {
    const value = row[name];
    return value === "" ? [] : [{ key: label.toLowerCase(), value }];
  });
  const own = Object.entries(row.grouping_fields ?? {})
    .filter(([, value]) => value !== "")
    .map(([key, value]) => ({ key, value }));
  return [...named, ...own];
}

/**
 * What a rule charges, formatted for whichever arithmetic it runs.
 *
 * ⚠ **THE BRANCH IS HERE ONCE BECAUSE IT WAS WRITTEN THREE TIMES.** The rules
 * table, the diff and the customer's inherited-rule summary each asked
 * `rate_structure === "fixed_component"` before it could pick a formatter, and
 * three copies of one question about one concept is how two of them come to
 * answer it differently. It takes the four arithmetic fields structurally, so a
 * rule row, a diff side and an inherited rule all satisfy it without having to
 * agree on a type name.
 */
export function ruleAmount(
  terms: {
    rate_structure: string;
    rate_per_unit_micros: number;
    unit_quantity: number;
    fixed_micros: number;
  },
  currency: string,
): string {
  return terms.rate_structure === "fixed_component"
    ? formatMicros(terms.fixed_micros, currency)
    : formatPrice(terms.rate_per_unit_micros, terms.unit_quantity, undefined, currency);
}

export type ChangeKind = BookChangeIn["kind"];

/**
 * What each of the three acts a change may be is called, on screen.
 *
 * ⚠ **CONSOLE COPY, NOT CATALOGUE CONTENT, AND THE DIFFERENCE IS THE REGISTRY'S
 * OWN RULING.** `BookChangeIn.kind` is deliberately a plain string on the wire:
 * the three words *"name the shape of one request body, they are stored on no
 * column and returned in no response, and a `Literal` here would publish an
 * enumeration the vocabulary registry does not own"*. A catalogue key must
 * decompose into a declared concept prefix and a declared value of it in both
 * directions (ADR-0008 §4), so there is no key for these to hang off and
 * `@/locales` is the wrong home. That puts them in the same category as
 * `SCHEDULE_REFUSALS` next door: console-owned wording, total over its own
 * value set, in ONE place.
 *
 * ⚠ **ONE PLACE, BECAUSE THERE WERE TWO AND THEY DISAGREED.** The dialog that
 * stages a change and the diff that renders one each had their own map, and
 * they read *"Add a rule"* against *"Adds a rule"* for the identical value.
 * Both forms are still here — a button OFFERS an act and a diff row REPORTS one
 * — but they are stated together, so a third surface cannot invent a third
 * wording and the pair cannot drift apart.
 */
export const CHANGE_KINDS = {
  add: {
    offer: "Add a rule",
    done: "Adds a rule",
    hint: "Price something this book does not price yet.",
  },
  reprice: {
    offer: "Reprice a rule",
    done: "Reprices",
    hint: "Change what an existing rule charges.",
  },
  retire: {
    offer: "Retire a rule",
    done: "Retires",
    hint: "Stop this book pricing it at all.",
  },
} as const satisfies Record<string, { offer: string; done: string; hint: string }>;

/**
 * What a change of this kind DID, for a diff row.
 *
 * An unrecognised kind renders as itself rather than as a guess — the wire's
 * own value is the only true thing the console knows about it, which is the
 * rule `@/lib/localisation` applies to every value the registry has not met.
 */
export function changeKindDone(kind: string): string {
  return kind in CHANGE_KINDS
    ? CHANGE_KINDS[kind as keyof typeof CHANGE_KINDS].done
    : kind;
}
