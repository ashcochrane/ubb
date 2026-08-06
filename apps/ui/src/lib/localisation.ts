// Strict label lookup — the console's only sanctioned way to turn a canonical
// value into words (#210, ADR-0008 §4).
//
// Registry value  ──▶  generated label key  ──▶  catalogue wording
//                      @/lib/vocabulary          @/locales
//
// THERE IS NO FALLBACK. `@/lib/labels` used to humanise anything it did not
// recognise, so the retired billing-mode token rendered as a title-cased copy
// of itself — user-facing terminology manufactured by a string transformation
// rather than chosen by anyone (ADR-0008 §4.3 spells that example out, and this
// comment deliberately does not repeat the retired word).
// ADR-0008 §4.3 reverses #154 §9.1 and calls that a defect. A value the registry
// declares and the catalogue does not carry fails CI (G6); if one somehow
// reaches this module at runtime it renders an explicit development error,
// never invented copy.
//
// The four outcomes are a discriminated union rather than four strings, because
// the difference between them is exactly what a caller may want to style
// differently — and because a test asserting on `kind` cannot pass by
// accidentally matching prose.

import { catalogue } from "@/locales";

/** What renders for a value that is absent, empty or null. */
export const ABSENT_LABEL = "—";

/** An explicit development error, for a declared value with no wording. */
export function missingLabel(key: string): string {
  return `[no label: ${key}]`;
}

export type LabelResolution =
  /** No value at all — not a defect, and not a name either. */
  | { readonly kind: "absent"; readonly text: string }
  /** The ordinary case: a declared value, and the catalogue's words for it. */
  | { readonly kind: "labelled"; readonly key: string; readonly text: string }
  /** A declared value with no wording. Impossible while G6 is green. */
  | { readonly kind: "unlabelled"; readonly key: string; readonly text: string }
  /** A value the registry has never seen — legal on an `open` concept (ADR-003). */
  | { readonly kind: "unfamiliar"; readonly value: string; readonly text: string };

/**
 * Resolve one value against one concept's generated label keys.
 *
 * ```ts
 * import { TASK_STATUS_LABEL_KEYS } from "@/lib/vocabulary";
 * resolveLabel(TASK_STATUS_LABEL_KEYS, "expired");  // → "Expired"
 * ```
 *
 * THE KIND IS DERIVED, NEVER DECLARED. A caller does not tell this function
 * whether the concept is open or closed, because the label-key map already
 * answers the only question that matters: a value the map knows is one the
 * registry declares, and a value it does not know is one the registry has never
 * seen. Asking the call site to restate the concept's kind would put a second
 * copy of a registry fact in the console — which is the drift this whole layer
 * exists to abolish.
 *
 * An unfamiliar value renders as ITSELF, verbatim. That is the deliberate
 * generic form ADR-0008 §4.4 asks for: the raw token is the only true thing UBB
 * knows about the value, and title-casing it would dress a foreign token up as
 * wording UBB authored — the precise failure this module replaces. A caller that
 * wants to mark it visually has `kind` to branch on.
 *
 * **This REVERSES the console's own standing rule**, and the reversal is
 * recorded rather than slipped through. `labels.ts` opened with *"never render a
 * raw snake_case/UPPER_SNAKE token"*, and that rule was right while its only
 * alternative was humanising: between a token and a title-cased token, the
 * token loses. ADR-0008 §4.3 removes the alternative, and the choice becomes a
 * different one — between the value the server actually sent and a placeholder
 * that discards it. A placeholder reads as authored copy for a case where UBB
 * has authored nothing, and it throws away the one thing an operator needs to
 * act on. So the token ships, and `kind: "unfamiliar"` is what lets a surface
 * present it as the foreign thing it is.
 */
export function resolveLabel(
  labelKeys: Readonly<Record<string, string>>,
  value: string | null | undefined,
): LabelResolution {
  if (value === null || value === undefined || value === "") {
    return { kind: "absent", text: ABSENT_LABEL };
  }
  const key = labelKeys[value];
  if (key === undefined) {
    return { kind: "unfamiliar", value, text: value };
  }
  const text = catalogue[key];
  if (text === undefined || text.trim() === "") {
    return { kind: "unlabelled", key, text: missingLabel(key) };
  }
  return { kind: "labelled", key, text };
}

/**
 * Bind a concept's label keys once, and get back the lookup its call sites use.
 *
 * ```ts
 * export const taskStatusLabel = labelMap(TASK_STATUS_LABEL_KEYS);
 * ```
 *
 * The same call shape as the legacy `@/lib/labels` maps on purpose: migrating a
 * vocabulary is then one line in one file, and every call site of the old label
 * function keeps working unchanged. What changes is what it does when it does
 * not recognise a value.
 */
export function labelMap(labelKeys: Readonly<Record<string, string>>) {
  return (value: string | null | undefined): string =>
    resolveLabel(labelKeys, value).text;
}
