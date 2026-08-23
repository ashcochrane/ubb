// What a refused effective instant means, in the console's own words.
//
// ⚠ **FOUR NAMED CODES, AND THE NAMING IS THE WHOLE REASON THEY EXIST.** The
// platform refuses an unhonourable instant with `effective_at_naive`,
// `effective_at_in_past`, `effective_at_too_far_ahead` or
// `effective_at_before_scheduled_boundary`, and `core/scheduling` says outright
// why each carries a code of its own: so that *"that date is a typo"* is
// distinguishable from *"that date has passed"* and from every other reason a
// body is refused. A console that rendered `problemMessage` for all four would
// throw away the distinction the codes were coined to draw — the tenant would
// read four refusals in the same tone and have to work out which one they had
// hit from the sentence.
//
// ⚠ **AND IT IS KEYED ON THE CODE, NEVER ON THE TEXT.** The server's detail is
// prose and prose is edited; the code is the contract. Matching on wording is
// how a console comes to render a fallback the day somebody improves a sentence.
//
// THE FALLBACK IS THE SERVER'S OWN MESSAGE, not a shrug: anything else refused
// here is a refusal this module has no special knowledge of, and the API's
// detail is the best thing anybody has to say about it.

import { ApiProblem, problemMessage } from "@/api/problem";

/**
 * The console's sentence for each named schedule refusal.
 *
 * Deliberately console copy rather than catalogue content, on the same rule
 * `PRICING_STATUS_EXPLANATIONS` follows: a catalogue key must decompose into a
 * declared concept prefix and a declared value of it, in both directions, and
 * "why this date was refused" decomposes to nothing.
 */
export const SCHEDULE_REFUSALS = {
  effective_at_too_far_ahead:
    "That date is more than 366 days away. The horizon is a platform limit and no setting moves it — it is there so a mistyped year cannot become a change nobody sees again.",
  effective_at_in_past:
    "That date has already passed. A change is dated forward or not at all: a boundary behind the present would reprice work that has already been recorded.",
  effective_at_naive:
    "That instant has no time zone, so it does not name a moment. Pick a date and time.",
  effective_at_before_scheduled_boundary:
    "This book already has a change scheduled after that date. Changes to one book are dated forwards — date this one on or after that change, or discard the scheduled change first.",
} as const;

export type ScheduleRefusalCode = keyof typeof SCHEDULE_REFUSALS;

/** True for one of the four instants this platform refuses by name. */
export function isScheduleRefusal(error: unknown): error is ApiProblem {
  return (
    error instanceof ApiProblem &&
    Object.prototype.hasOwnProperty.call(SCHEDULE_REFUSALS, error.code)
  );
}

/**
 * What to show a tenant whose change was refused.
 *
 * One function rather than a lookup plus a guard at each call site: three
 * dialogs declare a dated change and all three owe the same answer, and the
 * one that forgot the guard would render the generic message for the one
 * refusal a tenant most needs told apart.
 */
export function scheduleRefusal(error: unknown): string {
  if (isScheduleRefusal(error)) {
    return SCHEDULE_REFUSALS[error.code as ScheduleRefusalCode];
  }
  return problemMessage(error);
}

/**
 * The instant a `datetime-local` control names, or `undefined` for "now".
 *
 * ⚠ **ONE PARSE, BECAUSE THE SECOND COPY HAD A BUG.** Two screens declare a
 * dated change — a change to a book, and a customer's own deal — and each had
 * its own derivation. Only one guarded `Number.isNaN`, so on the other a
 * half-typed date reached `new Date(...).toISOString()` and threw `RangeError`
 * rather than being ignored.
 *
 * ⚠ **AN UNPARSEABLE INSTANT MEANS "NOT STATED", NOT "NOW".** `undefined` is
 * what a body sends for an immediate change, so the two are the same value on
 * the wire — which is right: a tenant mid-way through typing a date has not
 * asked for anything yet, and the submit button is what decides whether an
 * unstated instant was the change they meant. This refuses nothing: the 366-day
 * horizon and every other bound stay the platform's, so a refusal a tenant sees
 * is always one of the four named ones above.
 *
 * It lives here rather than beside the control it is read by, because a module
 * that exports a component and a function alike breaks fast refresh — and
 * because this is the same subject the four refusals are: what this platform
 * does with an instant.
 */
export function effectiveInstant(local: string): string | undefined {
  if (local === "") return undefined;
  const parsed = new Date(local);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
}
