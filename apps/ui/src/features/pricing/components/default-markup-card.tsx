import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { formatPercentMicros } from "@/lib/format";
import { toastOnError, toastSuccess } from "@/lib/mutations";
import {
  useDeclareTenantDefaultMarkup,
  useTenantDefaultMarkup,
  useWithdrawTenantDefaultMarkup,
} from "../api/queries";
import { microsToUnitString, toMicros } from "../lib/pricing-math";
import { markupFormSchema, type MarkupFormValues } from "../lib/schemas";

/**
 * The tenant's declared default markup rung — the last rung, and what prices an
 * event no rule matched.
 *
 * ⚠ **NO DECLARATION IS NOT A ZERO, AND THIS CARD IS WHERE A TENANT LEARNS
 * THAT.** A declared zero says *charge my customer exactly what the call cost*
 * and settles; no declaration at all means nobody has said what to charge, so
 * the price resolves to `unknown` with no amount and the event waits. Rendering
 * `0%` for an absent declaration would be the same defect as rendering `£0.00`
 * for an absent price, one concept up — and it would tell a tenant they had
 * decided something they have not.
 *
 * ⚠ **AND WITHDRAWING IS A DIFFERENT ACT FROM DECLARING ZERO**, which is why
 * there are two controls rather than an empty box. Typing nothing cannot mean
 * "withdraw", because typing nothing is also what a half-finished edit looks
 * like.
 *
 * ⚠ **IT SAYS THE RUNG IS NOT A MULTIPLIER.** The explainer above it makes the
 * same point about the ladder as a whole; this card makes it beside the number,
 * because a percentage on a pricing page is exactly where a reader reaches for
 * "and then everything gets multiplied by this".
 */
export function DefaultMarkupCard() {
  const isAdmin = useHasRole("admin");
  const markup = useTenantDefaultMarkup();
  const declare = useDeclareTenantDefaultMarkup();
  const withdraw = useWithdrawTenantDefaultMarkup();
  const [editing, setEditing] = React.useState(false);
  // ⚠ WITHDRAWING IS CONFIRMED BECAUSE IT IS THE ONE ACT ON THIS CARD THAT
  // CHANGES WHAT HAPPENS TO EVENTS NOBODY HAS PRICED. Declaring a percentage
  // moves a number; withdrawing removes the rung, and every event no rule
  // matches then resolves to `unknown` with no amount billed at all. That is
  // the consequence copy the console's UX rule asks for — and it is also the
  // sentence that stops a reader assuming withdrawal is the same as zero.
  const [withdrawing, setWithdrawing] = React.useState(false);

  const form = useForm<MarkupFormValues>({
    resolver: zodResolver(markupFormSchema),
    defaultValues: { markup_percent: "" },
  });

  const declared = markup.data?.markup_micro_percent;
  const hasRung = declared != null;

  const startEditing = () => {
    form.reset({
      // Both directions through the module that owns the conversion: a local
      // `declared / 1_000_000` here and `toMicros` on submit would be two
      // rounding rules for one field, and only one of them tested.
      markup_percent: hasRung ? microsToUnitString(declared) : "",
    });
    declare.reset();
    setEditing(true);
  };

  const onSubmit = (values: MarkupFormValues) => {
    declare.mutate(
      { markup_micro_percent: toMicros(values.markup_percent) },
      {
        onSuccess: () => {
          toastSuccess("Markup declared", "Events no rule prices use this rung.");
          setEditing(false);
        },
        onError: toastOnError("Couldn't declare the markup"),
      },
    );
  };

  return (
    <Card size="sm">
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-text-primary">
              Your default markup
            </p>
            <p className="max-w-2xl text-[12px] leading-relaxed text-text-secondary">
              The last rung of the ladder: what a customer is charged for an
              event no rule priced. It is taken over what the provider charged
              you — never on top of a rule’s own price.
            </p>
          </div>
          {!editing && (
            <div className="flex items-center gap-2">
              <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
                <Button size="sm" onClick={startEditing} disabled={!isAdmin}>
                  {hasRung ? "Change" : "Declare a markup"}
                </Button>
              </DisabledHint>
              {hasRung && (
                <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!isAdmin || withdraw.isPending}
                    onClick={() => setWithdrawing(true)}
                  >
                    Withdraw
                  </Button>
                </DisabledHint>
              )}
            </div>
          )}
        </div>

        {markup.isLoading ? (
          <Skeleton className="h-8 w-40" />
        ) : markup.isError ? (
          <ErrorCard
            error={markup.error}
            onRetry={() => void markup.refetch()}
            title="Couldn't load your default markup"
          />
        ) : editing ? (
          <form
            onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
            className="space-y-3"
          >
            <FormField
              label="Markup (%)"
              error={form.formState.errors.markup_percent?.message}
              hint="A percentage on top of what the call cost you. There is no floor, no cap and no per-event addend — a margin never composes."
            >
              {(id) => (
                <Input
                  id={id}
                  inputMode="decimal"
                  className="w-[160px]"
                  {...form.register("markup_percent")}
                />
              )}
            </FormField>
            <div className="flex items-center gap-2">
              <Button type="submit" size="sm" disabled={declare.isPending}>
                {declare.isPending ? "Working…" : "Declare"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setEditing(false)}
                disabled={declare.isPending}
              >
                Cancel
              </Button>
            </div>
          </form>
        ) : hasRung ? (
          <div className="flex items-center gap-2">
            <span className="text-xl font-semibold tracking-tight">
              {formatPercentMicros(declared)}
            </span>
            <Badge variant="secondary">Declared</Badge>
          </div>
        ) : (
          <div className="space-y-1">
            <Badge variant="outline">Nothing declared</Badge>
            <p className="max-w-2xl text-[12px] leading-relaxed text-text-secondary">
              You have not declared a markup, which is not the same as declaring
              zero. Any event no rule prices resolves to{" "}
              <strong className="font-medium text-text-primary">unknown</strong>
              : no amount is billed, and it stays out of every revenue total
              until somebody says what to charge.
            </p>
          </div>
        )}
      </CardContent>

      <ConfirmDialog
        open={withdrawing}
        onOpenChange={setWithdrawing}
        title="Withdraw your default markup?"
        description="Every event no rule prices will resolve to unknown — no amount billed, and left out of every revenue total until somebody says what to charge. This is NOT the same as declaring 0%, which would charge your customers exactly what your calls cost."
        confirmLabel="Withdraw"
        destructive
        pending={withdraw.isPending}
        onConfirm={() =>
          withdraw.mutate(undefined, {
            onSuccess: () => {
              setWithdrawing(false);
              toastSuccess(
                "Markup withdrawn",
                "Events no rule prices now resolve to unknown — not to zero.",
              );
            },
            onError: toastOnError("Couldn't withdraw the markup"),
          })
        }
      />
    </Card>
  );
}
