// The console's grouping vocabulary, in one place (#506; slice 7 §6/§7).
//
// One request word names an axis — `field:<name>` or `rollup:<name>` — and its
// KIND is part of the word rather than metadata beside it, because a field is a
// column and a rollup is a join, with different cardinality and cost (§6). This
// module is where that word is built, read and worded.
//
// WHAT REPLACED WHAT. `@/lib/labels` used to carry two hand-written axis lists
// and a map wording them, and three of the six words it held were `dim1`–`dim3`
// — slot names, offered to every tenant, for axes no tenant had declared. The
// list is now the tenant's own, computed per tenant and read off the discovery
// contract (`useGroupingOptions`); this module holds only what turns one of its
// rows into words.
//
// ⚠ **WHERE EACH WORD COMES FROM.** A picker row needs four kinds of word. Three
// are UBB's and are the localisation layer's, reached the ordinary way —
// identity from `@/lib/vocabulary`, expression from `@/locales` (ADR-0008 §4):
//
//   * the two KINDS (`field` / `rollup`) — `analytics_grouping_kind`, bound
//     where the mark renders, in `components/shared/grouping-axis-label.tsx`;
//   * the two ROLLUP axes — `analytics_rollup`, resolved by `axisName` below
//     so that a rollup this build predates falls to the unworded branch rather
//     than to a guess;
//   * UBB's five RESERVED axes — `reserved_grouping_axis`, resolved the same
//     way and for the same reason.
//
// The fourth is a TENANT's own axis, which is not UBB's to word at all. It
// renders exactly as the tenant declared it, which is what the contract sends
// in `label`.
//
// ⚠ **THE FIVE WERE CONSOLE COPY UNTIL #575, AND THE REASON THEY WERE IS WORTH
// KEEPING.** They were authored in this file as an object literal, because the
// registry declares concepts by their VALUES and these read as the names of
// fields — the same kind of thing as a column heading. The note that stood here
// ended "nobody owns the question yet". The owner then ruled them canonical
// (#544): the server reserves them, a client sends them as the name half of the
// request word, and the discovery contract publishes them, so they ARE values —
// of `reserved_grouping_axis`. Their identity is generated into
// `@/lib/vocabulary` and their wording lives in the catalogue, which is also
// what the pricing feature's rate selectors read four of them through
// (`selectorTitle` in `features/pricing/lib/rules.ts`).

import { resolveLabel } from "@/lib/localisation";
import type { MeteringSchemas } from "@/api/types";
import {
  ANALYTICS_GROUPING_KIND_VALUES,
  ANALYTICS_ROLLUP_LABEL_KEYS,
  RESERVED_GROUPING_AXIS_LABEL_KEYS,
  type ReservedGroupingAxis,
} from "@/lib/vocabulary";

/** One axis this tenant may group by, exactly as the discovery contract states it. */
export type GroupingOption = MeteringSchemas["GroupingOptionOut"];

/** The separator between an axis's kind and its own name, in the one request word. */
const KIND_SEPARATOR = ":";

/** One of the two kinds, as the request spells it. */
export type GroupingKind = (typeof ANALYTICS_GROUPING_KIND_VALUES)[number];

/**
 * The two kinds by name, for the call sites that know which one they mean.
 *
 * ⚠ **TYPED AGAINST THE GENERATED SET, WHICH IS AS TIGHT AS THIS GETS.** The
 * registry generates the value set and the label keys but no per-value
 * constant, so the two names are spelled here once — and the annotation makes
 * `tsc` refuse a spelling the registry does not declare, rather than leaving
 * two string literals agreeing with it by luck. `grouping-axis.test.ts` also
 * asserts the pair IS the whole set, so a third kind is a red test rather than
 * a word this module silently never offers.
 */
export const FIELD_KIND: GroupingKind = "field";
export const ROLLUP_KIND: GroupingKind = "rollup";

/**
 * One of the axes every tenant has, whatever it declares.
 *
 * The registry's `reserved_grouping_axis`, under the name this console's call
 * sites already use. The server's `RESERVED_KEYS` is generated from the same
 * declaration, so neither side keeps a list the other could drift from: a sixth
 * is declared once, in `domain-vocabulary/`, and arrives here as a wider union
 * with a label key the catalogue is then required to word (G6).
 *
 * ⚠ **FOUR OF THESE ALSO LABEL A RULE'S SELECTORS (#509)**, so rewording one in
 * the catalogue rewords the pricing screens too. The customer is the one that
 * does not: it is an axis a report groups by and never something a rule selects
 * on, and `tests/contracts/test_rate_selector_vocabulary.py` holds the pricing
 * feature's list to the server's selectors so it cannot come back that way.
 */
export type UbbAxis = ReservedGroupingAxis;

/** Whether an axis name off the wire is one UBB reserves, and so has UBB's word. */
export function isUbbAxis(name: string): name is UbbAxis {
  return Object.hasOwn(RESERVED_GROUPING_AXIS_LABEL_KEYS, name);
}

/**
 * UBB's word for one of its own axes, where the caller knows it has one.
 *
 * The typed form, for a surface naming the axes it offers rather than reading
 * them off the contract: a name the registry does not reserve is a `tsc`
 * failure at that call site instead of a blank in a picker.
 */
export function ubbAxisTitle(axis: UbbAxis): string {
  return resolveLabel(RESERVED_GROUPING_AXIS_LABEL_KEYS, axis).text;
}

/**
 * How an axis's own name is to be shown, and on whose authority.
 *
 * `kind` is what a caller branches on to decide the rendering, and it is
 * derived here rather than declared at the call site so that two pickers cannot
 * answer the same row two different ways:
 *
 *   `worded`   UBB has a word for this axis, and the catalogue carries it — a
 *              rollup's, or a reserved field's.
 *   `tenant`   the tenant's own key, sent on the row. Rendered verbatim.
 *   `unworded` nothing has a word for it. The token is the only true thing
 *              known about it, and the call site marks it as unrecognised
 *              through the open-set helper rather than humanising it.
 */
export type AxisName =
  | { readonly kind: "worded"; readonly text: string }
  | { readonly kind: "tenant"; readonly text: string }
  | { readonly kind: "unworded"; readonly text: string };

export function axisName(option: GroupingOption): AxisName {
  if (option.rollup !== null && option.rollup !== undefined) {
    const resolved = resolveLabel(ANALYTICS_ROLLUP_LABEL_KEYS, option.rollup);
    return resolved.kind === "labelled"
      ? { kind: "worded", text: resolved.text }
      : { kind: "unworded", text: option.rollup };
  }
  if (option.label !== "") return { kind: "tenant", text: option.label };
  const name = axisNameOf(option.key);
  return isUbbAxis(name)
    ? { kind: "worded", text: ubbAxisTitle(name) }
    : { kind: "unworded", text: name };
}

/** The axis's own name, with its kind taken off the front. */
export function axisNameOf(requestWord: string): string {
  const cut = requestWord.indexOf(KIND_SEPARATOR);
  return cut === -1 ? requestWord : requestWord.slice(cut + 1);
}

/** The one request word for an axis: its kind, then the axis's own name. */
export function axisRequestWord({ kind, name }: { kind: string; name: string }): string {
  return `${kind}${KIND_SEPARATOR}${name}`;
}

/**
 * The kind a request word declares, or `undefined` where it declares none.
 *
 * ⚠ **THE PREFIX IS CHECKED AGAINST THE REGISTRY'S OWN SET, NOT AGAINST TWO
 * LITERALS.** `ANALYTICS_GROUPING_KIND_VALUES` is generated from
 * `domain-vocabulary/`, so a third kind is accepted here the day the registry
 * declares one, and a word this console invents is refused today.
 */
export function groupingKindOf(requestWord: string): string | undefined {
  const cut = requestWord.indexOf(KIND_SEPARATOR);
  if (cut <= 0 || cut === requestWord.length - 1) return undefined;
  const kind = requestWord.slice(0, cut);
  return (ANALYTICS_GROUPING_KIND_VALUES as readonly string[]).includes(kind)
    ? kind
    : undefined;
}

/**
 * Whether a string is shaped like an axis this server could accept.
 *
 * A SHAPE check and deliberately not a membership one: which axes exist is the
 * tenant's own answer and the discovery contract's to give, so a URL parser has
 * no business deciding it and the server refuses an axis nobody declared. What
 * this catches is the shape the retired vocabulary sent — a bare axis name the
 * call site prefixed — which names no axis at all.
 */
export function isGroupingAxis(value: string): boolean {
  return groupingKindOf(value) !== undefined;
}
