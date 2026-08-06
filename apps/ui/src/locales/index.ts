// The console's label catalogues — the localisation layer ADR-0008 §4 splits out.
//
// The registry (`domain-vocabulary/` at the git root) owns IDENTITY: which
// concepts exist, what values they take, and the stable key each value's
// wording hangs on. Those keys arrive here already generated, in
// `@/lib/vocabulary`. This directory owns EXPRESSION: the words themselves.
//
// The split is not tidiness. Wording, capitalisation and translation change far
// more often than the token underneath, and a vocabulary file that became the
// copy deck would either turn into an i18n database or privilege English inside
// the domain model.
//
// A catalogue is JSON rather than TypeScript so that the gate proving it
// complete can read it without a TypeScript parser: `tests/contracts` is
// deliberately Node-free, and the one artifact that must never drift should not
// depend on the most fragile way of reading it (#158 §4.1 writes it as JSON for
// the same reason).
//
// ADDING A LOCALE is two acts: the file, and an `import` below. CI fails on
// either alone — an unimported catalogue ships to nobody while satisfying
// "every supported locale carries the key", and an import with no file is a
// build break the gate should name rather than leave to `tsc`. It then fails
// again unless the new catalogue carries every required key, which is what
// makes a half-translated locale impossible to ship rather than merely
// discouraged.

import en from "./en.json";

/** Every catalogue that ships, by locale. The import list above is the declaration. */
export const LOCALES = { en } as const;

export type SupportedLocale = keyof typeof LOCALES;

/** The locale every other one is measured against, and the only one today. */
export const DEFAULT_LOCALE: SupportedLocale = "en";

/**
 * The catalogue lookups read.
 *
 * A module-level constant rather than a React context: there is no locale
 * switcher, and inventing the plumbing for one now would be scaffolding with no
 * user. The seam that matters — a lookup that consults a catalogue by key — is
 * already here, so adding the switcher later changes this line and nothing at
 * any call site.
 */
export const catalogue: Readonly<Record<string, string>> = LOCALES[DEFAULT_LOCALE];
