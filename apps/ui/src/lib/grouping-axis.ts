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
// ⚠ **WHERE EACH WORD COMES FROM, AND THE ONE SET THAT HAS NO REGISTRY HOME.**
// A picker row needs four kinds of word, and three of them are the localisation
// layer's, reached the ordinary way — identity from `@/lib/vocabulary`,
// expression from `@/locales` (ADR-0008 §4):
//
//   * the two KINDS (`field` / `rollup`) — `analytics_grouping_kind`, bound
//     where the mark renders, in `components/shared/grouping-axis-label.tsx`;
//   * the two ROLLUP axes — `analytics_rollup`, resolved by `axisName` below
//     so that a rollup this build predates falls to the unworded branch rather
//     than to a guess;
//   * a TENANT's own axis — not UBB's to word at all. It renders exactly as the
//     tenant declared it, which is what the contract sends in `label`.
//
// The fourth is UBB's five reserved axes, and they are authored below as
// CONSOLE COPY rather than catalogue wording. The reason is that the registry
// declares concepts by their VALUES, and these five are not values — they are
// the names of fields, the same kind of thing as the column headings this
// console already authors ("Kind of work" over the runs table, "Event type"
// over the ledger). G6 refuses a catalogue key no concept declares, so wording
// them there would mean coining a registry concept for a set of field names,
// which is a registry act and not a console one.
//
// ⚠ **AND THE CONTRACT WAS SAYING SOMETHING ELSE.** `GroupingOptionOut`'s
// published description used to end that rule with *"UBB's own wording for its
// own axes lives in the localisation layer"* — false the moment the five were
// authored here, and shipped in `openapi/v1.json` to every tenant. It now says
// what is actually true of any client: the registry owns identity, the surface
// that renders an axis owns its expression, and UBB does not derive English
// from its own token and publish it as though somebody had chosen it. That is
// a better sentence for a CONTRACT anyway — where a particular console keeps
// its copy was never a tenant's business.
//
// ⚠ **RESIDUAL, recorded rather than left for a reader to notice.** These five
// still are not registry-declared, so nothing generates them, and the only
// thing tying them to the server is the cross-tree check named at
// `UBB_AXIS_TITLES` rather than anything a generator would refuse. If a concept
// is ever coined for UBB's own axis names, the catalogue becomes their home and
// this object goes. The residual now covers the pricing feature's rate
// selectors too: #509 took four of these words for them (`selectorTitle` in
// `features/pricing/lib/rules.ts`) rather than keeping a second copy there, so
// the same answer will serve both. Nobody owns the question yet.

import { resolveLabel } from "@/lib/localisation";
import type { MeteringSchemas } from "@/api/types";
import {
  ANALYTICS_GROUPING_KIND_VALUES,
  ANALYTICS_ROLLUP_LABEL_KEYS,
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
 * UBB's words for the five axes every tenant has, whatever it declares.
 *
 * These are the server's `RESERVED_KEYS`, and the discovery contract sends them
 * with an empty `label` precisely because their wording is UBB's rather than
 * the tenant's.
 *
 * ⚠ **THE AGREEMENT WITH THAT LIST IS CHECKED, AND NOT FROM HERE.** A vitest
 * case comparing this map against five literals typed beside it would be one
 * party to an agreement checking its own side, and a sixth reserved word on the
 * server would be invisible to it. `tests/contracts/
 * test_grouping_axis_vocabulary.py` reads BOTH trees as text — the Python with
 * `ast`, this object with a regex — and pins the two sets equal in both
 * directions: an axis the server offers with no word here would render as a
 * marked token instead of the word UBB chose, and a word here for an axis the
 * server never offers is copy no render can reach.
 *
 * ⚠ **FOUR OF THESE WORDS ALSO LABEL A RULE'S SELECTORS (#509)**, so changing
 * one changes the pricing screens too. The customer is the one that does not:
 * it is an axis a report groups by and never something a rule selects on, and
 * `tests/contracts/test_rate_selector_vocabulary.py` holds the pricing
 * feature's list to the server's selectors so it cannot come back that way.
 */
export const UBB_AXIS_TITLES = {
  customer: "Customer",
  provider: "Provider",
  event_type: "Event type",
  task_type: "Kind of work",
  subtask_type: "Kind of subtask",
} as const;

/** One of the axes every tenant has, whatever it declares. */
export type UbbAxis = keyof typeof UBB_AXIS_TITLES;

/**
 * UBB's word for one of its own axes, where the caller knows it has one.
 *
 * The typed form, for a surface naming the axes it offers rather than reading
 * them off the contract: a name with no word here is a `tsc` failure at that
 * call site instead of a blank in a picker.
 */
export function ubbAxisTitle(axis: UbbAxis): string {
  return UBB_AXIS_TITLES[axis];
}

/** The same lookup over an axis name off the wire, which may be one UBB has no word for. */
function titleForAxisNamed(name: string): string | undefined {
  return (UBB_AXIS_TITLES as Readonly<Record<string, string | undefined>>)[name];
}

/**
 * How an axis's own name is to be shown, and on whose authority.
 *
 * `kind` is what a caller branches on to decide the rendering, and it is
 * derived here rather than declared at the call site so that two pickers cannot
 * answer the same row two different ways:
 *
 *   `worded`   UBB has a word for this axis — the catalogue's for a rollup, the
 *              authored one above for a reserved field.
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
  const title = titleForAxisNamed(name);
  return title === undefined
    ? { kind: "unworded", text: name }
    : { kind: "worded", text: title };
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
