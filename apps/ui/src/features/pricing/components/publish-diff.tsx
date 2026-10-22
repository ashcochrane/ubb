import { Badge } from "@/components/ui/badge";
import { pricingMethodLabel } from "@/lib/customer-price";
import { formatParsedMicros } from "@/lib/format";
import { ABSENT_LABEL, tenantDefinedLabel } from "@/lib/localisation";
import type {
  AgreedPriceTerms,
  BookAgreedPriceChangeDiff,
  BookChangeDiff,
  BookRateChangeDiff,
  RuleTerms,
} from "../api/types";
import {
  agreedPriceChangeKindDone,
  changeKindDone,
  pinnedInDiff,
  rateStructureLabel,
  ruleAmount,
} from "../lib/rules";

/**
 * A draft's diff — what the book will look like afterwards.
 *
 * ⚠ **IT RENDERS THE SERVICE'S ANSWER AND COMPUTES NOTHING.** The diff arrives
 * on the declare response, resolved against the book as it will stand at the
 * effective instant — which the console cannot see, because a change scheduled
 * between now and then moves what `before` is. A console that diffed the rules
 * it happened to have cached would show a tenant a comparison against the wrong
 * book and call it the outcome.
 *
 * ⚠ **A ROW IS READ AS A CHANGE, NOT AS AN OUTCOME**, which is why `before` and
 * `after` sit side by side even where one of them is null. An add has no
 * before, a retire has no after, and a reprice has both — so the shape of the
 * row already says which of the three acts it is, before the word does.
 *
 * ⚠ **TWO KINDS OF ROW, TOLD APART BY `line` (#553).** A rate's row names the
 * quantity and the selectors it pins; an agreed price's names the kind of work
 * and nothing else, because one agreed price buys a whole unit of that kind.
 * Each is narrowed before anything only it carries is read.
 */
export function PublishDiff({
  rows,
  currency,
  unavailableReason,
}: {
  rows: readonly BookChangeDiff[] | null | undefined;
  currency: string;
  unavailableReason?: string | null;
}) {
  if (rows == null) {
    return (
      <p className="text-[12px] text-text-muted">
        {unavailableReason
          ? `No diff for this change: ${unavailableReason}`
          : // The ordinary case, and not an error: a published record's diff is
            // null because the record now says what it DID — which rules it
            // closed and which it opened — rather than what it intended to.
            "This change has been published. What it did is in the rules below and in the governance trail."}
      </p>
    );
  }
  if (rows.length === 0) {
    return <p className="text-[12px] text-text-muted">This change does nothing.</p>;
  }
  return (
    <ul className="space-y-2">
      {rows.map((row, index) =>
        row.line === "agreed_price" ? (
          <AgreedPriceRow key={`agreed-${row.task_type}-${index}`} row={row} currency={currency} />
        ) : (
          <RateRow key={`rate-${row.measurement_key}-${index}`} row={row} currency={currency} />
        ),
      )}
    </ul>
  );
}

function RateRow({ row, currency }: { row: BookRateChangeDiff; currency: string }) {
  return (
    <li className="rounded-md border border-border px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <ChangeKind kind={row.kind} />
        <span className="font-mono text-[12px] text-text-primary">
          {row.measurement_key}
        </span>
        <DiffSelectors row={row} />
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px]">
        <Terms terms={row.before} currency={currency} muted />
        <span aria-hidden="true" className="text-text-muted">
          →
        </span>
        <Terms terms={row.after} currency={currency} />
      </div>
    </li>
  );
}

/**
 * An agreed price's row: the kind of work, and what one delivered unit of it
 * sells for on each side. The kind is the tenant's own word, rendered as they
 * declared it, and the price is shown to the micro wherever the parsed figure
 * holds it (`formatParsedMicros`) — an agreed price may be below a cent, and a
 * cent-rounded figure would show two different prices as one.
 */
function AgreedPriceRow({
  row,
  currency,
}: {
  row: BookAgreedPriceChangeDiff;
  currency: string;
}) {
  return (
    <li className="rounded-md border border-border px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="text-[10px]">
          {agreedPriceChangeKindDone(row.kind)}
        </Badge>
        <span className="text-[12px] text-text-secondary">for</span>
        <span className="font-mono text-[12px] text-text-primary">
          {tenantDefinedLabel(row.task_type)}
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px]">
        <AgreedPrice terms={row.before} currency={currency} muted />
        <span aria-hidden="true" className="text-text-muted">
          →
        </span>
        <AgreedPrice terms={row.after} currency={currency} />
      </div>
    </li>
  );
}

function AgreedPrice({
  terms,
  currency,
  muted,
}: {
  terms: AgreedPriceTerms | null;
  currency: string;
  muted?: boolean;
}) {
  if (terms == null) {
    return (
      <span className="text-text-muted" title="No agreed price on this side">
        {ABSENT_LABEL}
      </span>
    );
  }
  return (
    <span className={muted ? "text-text-muted" : "text-text-primary"}>
      <span className="font-medium">
        {formatParsedMicros(terms.agreed_price_micros, currency)}
      </span>
      <span className="ml-1.5 text-[11px]">per delivered run</span>
    </span>
  );
}

/** Which of the three acts a row is, in the words the tenant reads elsewhere. */
function ChangeKind({ kind }: { kind: string }) {
  return (
    <Badge variant="outline" className="text-[10px]">
      {changeKindDone(kind)}
    </Badge>
  );
}

/**
 * What the changed rule pins, in the tenant's own words.
 *
 * Through the same helper the rules table's rows use, so two screens describing
 * one rule cannot come to name its columns differently — which they had, at
 * `event=` against `event type=`.
 */
function DiffSelectors({ row }: { row: BookRateChangeDiff }) {
  const pins = pinnedInDiff(row);
  if (pins.length === 0) {
    return <span className="text-[11px] text-text-muted">any event</span>;
  }
  return (
    <span className="flex flex-wrap gap-1">
      {pins.map((pin) => (
        <span key={pin.key} className="text-[11px] text-text-secondary">
          <span className="text-text-muted">{pin.key}=</span>
          <span className="font-mono">{pin.value}</span>
        </span>
      ))}
    </span>
  );
}

/**
 * One side of a change: what the rule charges, how it derives it, and which
 * arithmetic it runs.
 *
 * ⚠ **THE ARITHMETIC SHAPE IS ALWAYS SHOWN, EVEN WHERE THE MONEY DID NOT MOVE.**
 * It decides which of the money terms is actually spent, so a rule going from a
 * per-unit charge to a fixed component would read as *"nothing moved"* from the
 * amounts alone — the contract's own note on `RuleTermsOut`, and the reason
 * this renders three facts rather than a number.
 */
function Terms({
  terms,
  currency,
  muted,
}: {
  terms: RuleTerms | null | undefined;
  currency: string;
  muted?: boolean;
}) {
  if (terms == null) {
    return (
      <span className="text-text-muted" title="No rule on this side">
        {ABSENT_LABEL}
      </span>
    );
  }
  const amount = ruleAmount(terms, currency);
  return (
    <span className={muted ? "text-text-muted" : "text-text-primary"}>
      <span className="font-medium">{amount}</span>
      <span className="ml-1.5 text-[11px]">
        {rateStructureLabel(terms.rate_structure)}
        {terms.pricing_method != null && (
          <> · {pricingMethodLabel(terms.pricing_method)}</>
        )}
      </span>
    </span>
  );
}
