import { Card, CardContent } from "@/components/ui/card";

/**
 * How a customer price is resolved, in the shape the resolver actually has.
 *
 * ⚠ **THIS REPLACES A PIPELINE THAT WAS FALSE FOR ANY TENANT WITH RULES.**
 * The explainer here used to read *base cost → markup → final charge*, three
 * steps with an arrow between them. The resolver does not do that: markup is a
 * RUNG, not a multiplier. It is what answers when no rule matched — it is never
 * applied on top of a rule's answer — so a tenant reading the old diagram would
 * expect their negotiated $4 per million to come out at $5.12 after a declared
 * 28%, and it comes out at $4. A drawing of a pipeline is a drawing of
 * something that does not happen.
 *
 * ⚠ **AND THE LADDER IS FOUR RUNGS WITH SPECIFICITY BEFORE SOURCE.** How
 * specifically a rule names the event is compared FIRST; where it came from is
 * only the tie-break inside a level (`pricing_service.ladder_rank`). The
 * alternative — the customer's own rules answering first at every level — was
 * the ladder as first stated and was rejected on its consequence: a customer's
 * blanket rule would shadow every specific price the tenant configured, so
 * agreeing one small discount would silently delete a catalogue. Getting the
 * order wrong on this card is not a wording defect; it is the console teaching
 * a tenant a rule that would lose them money.
 */

/** The ladder, most specific first — `ladder_rank`'s four rungs, in its order. */
const RUNGS = [
  {
    title: "This customer’s own rule for this exact usage",
    body: "A rule in the customer’s own pricing book that names the same event type, provider and grouping values.",
  },
  {
    title: "The selected book’s rule for this exact usage",
    body: "The same match, in the book their plan prices from or in your workspace default.",
  },
  {
    title: "This customer’s blanket rule",
    body: "A rule of theirs that pins less — it prices the measurement whatever the event type or grouping values.",
  },
  {
    title: "The selected book’s default rule",
    body: "The broadest match in the book selected for them. Nothing below this is a rule.",
  },
] as const;

export function HowPricingResolves() {
  return (
    <Card size="sm">
      <CardContent>
        <p className="mb-1 text-[13px] font-medium text-text-primary">
          How a price is resolved
        </p>
        <p className="mb-3 max-w-3xl text-[12px] leading-relaxed text-text-secondary">
          Books are chosen for the customer first — their own, the one their
          plan prices from, and your workspace default — and then{" "}
          <strong className="font-medium text-text-primary">
            every rule in all of them competes in one ranking
          </strong>
          . How specifically a rule names the event decides it; which book the
          rule came from is only the tie-break between two equally specific
          rules.
        </p>
        <ol
          aria-label="The pricing ladder"
          className="flex flex-col gap-3 sm:flex-row sm:gap-5"
        >
          {RUNGS.map((rung, index) => (
            <li key={rung.title} className="flex min-w-0 flex-1 gap-2.5">
              <span
                aria-hidden="true"
                className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-bg-subtle text-[11px] font-semibold text-text-secondary"
              >
                {index + 1}
              </span>
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-text-primary">
                  {rung.title}
                </p>
                <p className="mt-0.5 text-[12px] leading-relaxed text-text-secondary">
                  {rung.body}
                </p>
              </div>
            </li>
          ))}
        </ol>
        <div className="mt-4 space-y-2 border-t border-border pt-3">
          <p className="max-w-3xl text-[12px] leading-relaxed text-text-secondary">
            <strong className="font-medium text-text-primary">
              There is no fallthrough between books.
            </strong>{" "}
            A book that holds no matching rule does not hand the question to the
            next book — the ranking already had every book’s rules in it. If no
            rule anywhere matched, no rule is the answer.
          </p>
          <p className="max-w-3xl text-[12px] leading-relaxed text-text-secondary">
            <strong className="font-medium text-text-primary">
              Your markup is a rung, not a multiplier.
            </strong>{" "}
            It answers only where no rule did: the price becomes what the
            provider charged you plus your declared percentage. It is never
            applied on top of a rule’s price — a rule that says $4 charges $4.
            With no markup declared, the price is{" "}
            <strong className="font-medium text-text-primary">unknown</strong>:
            nobody has said what to charge, so no amount is billed and the event
            waits for one.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
