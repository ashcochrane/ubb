// The customer's revenue panels (#508; slice 7 §5, §9).
//
// WHAT STOOD HERE BEFORE AND WHY THIS IS NOT IT. The module held two cards
// until slice 7 emptied it: one wrote a recurring amount per customer (#496)
// and one set a customer-level switch deciding whether that customer's usage
// was revenue at all (#497). Both were coarse answers to questions UBB already
// answered precisely — the second per posting, the first not at all, because a
// single recurring amount has no periods, no source reference, and was summed
// into the same field as a Stripe subscription, destroying its provenance the
// moment it landed. What replaces them is a RECORD: one figure per period,
// carrying the span it covers, how it is spread, and where it came from.
//
// ⚠ **NOTHING HERE MAY READ AS A CHARGE.** UBB neither created nor invoiced
// this money. The tenant bills its customers somewhere UBB cannot see and is
// stating the figure so margin can be computed at the scope it was supplied
// at — so every panel says whose number it is, and no amount is rendered
// without its source reference beside it.
//
// ⚠ **BOTH POSTURES ARE FIRST-CLASS AND THE EMPTY ANSWER IS NOT AN EMPTY
// STATE.** #153 §3.2 rules that a tenant which does not bill through UBB may
// legitimately operate either way: cost tracking alone, or cost tracking plus
// supplied revenue. A customer nobody has supplied a figure for has revenue
// UBB does not know — margin unavailable at this scope, **never zero** — and
// saying so is the answer rather than a gap to fill. There is no call to
// action, no nudge and no empty-state illustration urging a tenant into a
// workflow they may have chosen against: supplying is a CAPABILITY, and the
// form below is available whether or not anything has been supplied.

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { Section } from "@/components/shared/section";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import type { DateRange } from "@/lib/date-range";
import { formatCalendarDate, formatMicros } from "@/lib/format";
import { toastSuccess } from "@/lib/mutations";
import { cn } from "@/lib/utils";
import {
  RECOGNITION_METHOD_VALUES,
  REVENUE_BASIS_VALUES,
  type RevenueBasis,
} from "@/lib/vocabulary";

import { useRecordSuppliedRevenue, useSuppliedRevenue } from "../api/queries";
import type { AttributedSuppliedRevenue } from "../api/types";
import { suppliedPeriod, toMicros } from "../lib/helpers";
import { suppliedRevenueSchema, type SuppliedRevenueForm } from "../lib/schemas";
import {
  RECOGNITION_METHOD_MEANS,
  recognitionMethodLabel,
  REVENUE_BASIS_MEANS,
  revenueBasisLabel,
  spreadsAcrossItsSpan,
} from "@/lib/supplied-revenue";

export const SUPPLIED_REVENUE_TITLE = "Revenue you supplied";
export const STATE_REVENUE_TITLE = "State what you earned";

/** The cost-tracking-only answer, said once so both halves of it agree. */
export const REVENUE_UNKNOWN_HERE =
  "Revenue unknown — nothing has been supplied covering this window.";
export const MARGIN_UNAVAILABLE_NOT_ZERO =
  "UBB is tracking this customer's cost. Margin is unavailable at this scope "
  + "rather than nil: revenue UBB does not know is not revenue of nothing.";

/**
 * How one supplied record's span reads, with the day count that settles it.
 *
 * The period end is EXCLUSIVE — the record's own field is, and so is every
 * window that reads it — so the date shown is the first day NOT covered. A
 * reader cannot be expected to know that, which is why the day count is beside
 * it and never optional: "14 Jun → 1 Jul" is ambiguous, "17 days" is not.
 */
function spanOf(record: AttributedSuppliedRevenue): string {
  const opens = formatCalendarDate(record.period_start);
  if (!record.period_end) return `${opens} · a single day`;
  const days = Math.round(
    (Date.parse(`${record.period_end}T00:00:00Z`)
      - Date.parse(`${record.period_start}T00:00:00Z`)) / 86_400_000,
  );
  return `${opens} → ${formatCalendarDate(record.period_end)} · ${days} days`;
}

/** One supplied record: its own figure, this window's share, and its provenance. */
function SuppliedRecordRow({
  record,
  basis,
}: {
  record: AttributedSuppliedRevenue;
  basis: RevenueBasis;
}) {
  // ⚠ **"DISTRIBUTED" IS A FACT ABOUT THIS ROW UNDER THIS BASIS, NOT A
  // COMPARISON OF TWO NUMBERS.** Reading it off `attributed !== amount` would
  // call a straight-line record undistributed whenever the window happened to
  // contain its whole span — true of the figure, false of the row, and it
  // would stop saying "spread" exactly where a reader most needs to know the
  // method is capable of it.
  const distributed = basis === "recognised" && spreadsAcrossItsSpan(record.recognition_method);
  return (
    <li
      data-supplied-record={record.id}
      data-distributed={distributed ? "yes" : "no"}
      className="flex flex-col gap-1 border-t border-border py-2 first:border-t-0 sm:flex-row sm:items-baseline sm:justify-between"
    >
      <div className="min-w-0">
        <p className="text-[13px] text-text-primary">{spanOf(record)}</p>
        {/* THE SOURCE REFERENCE IS NEVER OPTIONAL AND NEVER A TOOLTIP. It is
            what lets a reader say where the number came from — the fact the
            recurring profile destroyed by summing its amount into the same
            column as a Stripe subscription — so it renders beside the figure
            at the same weight as the period. */}
        <p className="text-[12px] text-text-secondary">
          From <span className="font-medium text-text-primary">{record.source_reference}</span>
          {" · "}
          {recognitionMethodLabel(record.recognition_method)}
        </p>
      </div>
      <div className="shrink-0 text-left sm:text-right">
        <p className="text-[13px] font-medium text-text-primary">
          {formatMicros(record.attributed_amount_micros, record.currency)}
          <span className="ml-1.5 text-[11px] font-normal text-text-muted">
            {revenueBasisLabel(basis).toLowerCase()}
          </span>
        </p>
        {distributed && (
          // NOTHING SILENTLY DISTRIBUTES. Where a method divides an amount, the
          // whole figure is shown beside the share so the division is visible
          // rather than inferred from a number that looks smaller than expected.
          <p className="text-[11px] text-text-secondary">
            share of {formatMicros(record.amount_micros, record.currency)} spread
            across its period
          </p>
        )}
      </div>
    </li>
  );
}

/** The basis the panel is reading under — a view, chosen, and always named. */
function BasisChoice({
  basis,
  onChoose,
}: {
  basis: RevenueBasis;
  onChoose: (next: RevenueBasis) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Revenue basis">
      {REVENUE_BASIS_VALUES.map((value) => (
        <button
          key={value}
          type="button"
          aria-pressed={value === basis}
          onClick={() => onChoose(value)}
          className={cn(
            "rounded border px-2 py-1 text-[12px]",
            value === basis
              ? "border-border-strong bg-bg-raised text-text-primary"
              : "border-border text-text-secondary",
          )}
        >
          {revenueBasisLabel(value)}
        </button>
      ))}
    </div>
  );
}

/** What the tenant has stated for this window, under a basis they choose. */
function SuppliedRevenuePanel({
  customerId,
  range,
  basis,
  onChooseBasis,
}: {
  customerId: string;
  range: DateRange;
  basis: RevenueBasis;
  onChooseBasis: (next: RevenueBasis) => void;
}) {
  const supplied = useSuppliedRevenue(customerId, range, basis);
  return (
    <Section
      title={SUPPLIED_REVENUE_TITLE}
      description="What you told UBB you earned from this customer, from your own billing. UBB neither created nor invoiced it."
    >
      <div className="space-y-3">
        <div>
          <BasisChoice basis={basis} onChoose={onChooseBasis} />
          <p className="mt-1 text-[11px] text-text-muted">{REVENUE_BASIS_MEANS[basis]}</p>
        </div>
        {supplied.isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : supplied.isError ? (
          <ErrorCard error={supplied.error} onRetry={() => void supplied.refetch()} />
        ) : supplied.data && supplied.data.records.length > 0 ? (
          // ⚠ **EVERY FIGURE IS LABELLED WITH THE BASIS THE ANSWER STATES, NOT
          // THE ONE THE PICKER IS SET TO, AND THE DIFFERENCE IS VISIBLE FOR AS
          // LONG AS A REFETCH TAKES.** The read keeps the previous answer on
          // screen while the next one loads (`keepPreviousData`), so between
          // the click and the response the rows below are the OLD basis's
          // figures — and labelling them from component state would put
          // "recognised" over undistributed numbers, which is precisely the
          // unlabelled proration §5 exists to end. The response carries its own
          // `basis` so that nothing has to assume; this is what that field is
          // for. Found by a test, by no gate.
          <>
            {/* THE TOTAL IS A LIST PER CURRENCY AND NEVER ONE FIGURE: a sum
                across currencies is a number true of neither, and this whole
                slice is about revenue figures that say what they are. */}
            <ul className="space-y-0.5">
              {supplied.data.totals.map((total) => (
                <li key={total.currency} data-supplied-total={total.currency}>
                  <span className="text-[18px] font-semibold text-text-primary">
                    {formatMicros(total.amount_micros, total.currency)}
                  </span>
                  <span className="ml-1.5 text-[12px] text-text-secondary">
                    {revenueBasisLabel(supplied.data.basis)} in this window
                  </span>
                </li>
              ))}
            </ul>
            <ul>
              {supplied.data.records.map((record) => (
                <SuppliedRecordRow
                  key={record.id}
                  record={record}
                  basis={supplied.data.basis}
                />
              ))}
            </ul>
          </>
        ) : (
          <div data-revenue="unknown" className="space-y-1">
            <p className="text-[13px] text-text-primary">{REVENUE_UNKNOWN_HERE}</p>
            <p className="text-[12px] text-text-secondary">{MARGIN_UNAVAILABLE_NOT_ZERO}</p>
          </div>
        )}
      </div>
    </Section>
  );
}

/** The write surface. **ADMIN floor**, mirroring the route's. */
function StateRevenuePanel({ customerId }: { customerId: string }) {
  const currency = useTenantCurrency();
  const isAdmin = useHasRole("admin");
  const mutation = useRecordSuppliedRevenue(customerId);
  // `form.*` rather than a destructure, which is this console's shape for a
  // form that reads its own live values (five other sections do it).
  const form = useForm<SuppliedRevenueForm>({
    resolver: zodResolver(suppliedRevenueSchema),
    defaultValues: {
      amount: "",
      month: "",
      began_on: "",
      recognition_method: "straight_line",
      source_reference: "",
    },
  });

  const { errors } = form.formState;
  const month = form.watch("month");
  const beganOn = form.watch("began_on");
  const method = form.watch("recognition_method");
  // The derived span, shown as it is typed. This is the affordance: the tenant
  // says which month and which day, and never works out that the fourteenth of
  // June is seventeen days (#153 §19(f)).
  const period = suppliedPeriod(month, beganOn);

  const submit = form.handleSubmit((values) => {
    const span = suppliedPeriod(values.month, values.began_on);
    if (span === null) return;
    mutation.mutate(
      {
        amount_micros: toMicros(values.amount),
        currency,
        period_start: span.period_start,
        period_end: span.period_end,
        recognition_method: values.recognition_method,
        source_reference: values.source_reference.trim(),
      },
      {
        onSuccess: () => {
          toastSuccess("Revenue recorded");
          form.reset();
        },
      },
    );
  });

  return (
    <Section
      title={STATE_REVENUE_TITLE}
      description="For a customer you bill outside UBB. One figure per period, with the reference it came from."
    >
      <form onSubmit={(event) => void submit(event)} className="space-y-3">
        <fieldset disabled={!isAdmin} className="space-y-3">
          <FormField label="Month this covers" error={errors.month?.message}>
            {(id) => <Input id={id} type="month" {...form.register("month")} />}
          </FormField>

          {/* THE MID-PERIOD AFFORDANCE. Leaving this blank means the whole
              month; filling it in is how "began on the fourteenth" is said,
              and the span underneath is derived rather than asked for. */}
          <FormField
            label="Day it started, if part-way through the month"
            error={errors.began_on?.message}
            hint="Leave blank for a whole month."
          >
            {(id) => <Input id={id} type="date" {...form.register("began_on")} />}
          </FormField>

          {period && (
            <p data-derived-period={period.partial ? "partial" : "whole"} className="text-[12px] text-text-secondary">
              {period.partial ? "Part period: " : "Whole month: "}
              {formatCalendarDate(period.period_start)} →{" "}
              {formatCalendarDate(period.period_end)} · {period.days} days
            </p>
          )}

          <FormField
            label={`Amount (${currency.toUpperCase()})`}
            error={errors.amount?.message}
            hint="Zero is a statement — a free period earned nothing, which is not the same as supplying nothing."
          >
            {(id) => <Input id={id} inputMode="decimal" {...form.register("amount")} />}
          </FormField>

          <fieldset className="space-y-1.5">
            <legend className="text-[13px] font-medium text-text-primary">
              How it is spread over the period
            </legend>
            {RECOGNITION_METHOD_VALUES.map((value) => (
              <label key={value} className="flex items-start gap-2 text-[12px]">
                <input
                  type="radio"
                  value={value}
                  {...form.register("recognition_method")}
                  className="mt-0.5"
                />
                <span>
                  <span className="font-medium text-text-primary">
                    {recognitionMethodLabel(value)}
                  </span>
                  <span className="mt-0.5 block text-text-secondary">
                    {RECOGNITION_METHOD_MEANS[value]}
                  </span>
                </span>
              </label>
            ))}
          </fieldset>

          <FormField
            label="Where it came from"
            error={errors.source_reference?.message}
            hint="Your own reference — an invoice number, a report. Re-using one for the same period restates that figure; a different one records another beside it."
          >
            {(id) => <Input id={id} {...form.register("source_reference")} />}
          </FormField>
        </fieldset>

        {period && !spreadsAcrossItsSpan(method) && (
          <p className="text-[11px] text-text-muted">
            This method lands the whole amount on {formatCalendarDate(period.period_start)}, so
            both views show the same figure for it.
          </p>
        )}

        <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
          <Button type="submit" disabled={!isAdmin || mutation.isPending}>
            {mutation.isPending ? "Working…" : "Record revenue"}
          </Button>
        </DisabledHint>
        {mutation.isError && (
          <p className="text-xs text-destructive">{problemMessage(mutation.error)}</p>
        )}
      </form>
    </Section>
  );
}

/**
 * The two panels, side by side: what has been supplied, and the surface that
 * supplies it.
 *
 * The basis is held HERE rather than inside the read panel, because it is the
 * question both halves are about: a tenant who has just stated a figure under
 * one view should see it land in that view.
 */
export function RevenuePanels({
  customerId,
  range,
}: {
  customerId: string;
  range: DateRange;
}) {
  const [basis, setBasis] = React.useState<RevenueBasis>("recorded");
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <SuppliedRevenuePanel
        customerId={customerId}
        range={range}
        basis={basis}
        onChooseBasis={setBasis}
      />
      <StateRevenuePanel customerId={customerId} />
    </div>
  );
}
