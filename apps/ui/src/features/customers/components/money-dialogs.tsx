// Top-up + withdraw dialogs. Idempotency keys are generated per dialog-open
// and REUSED on retry after a failure (replay-safe); a new key only appears
// on the next open (mutations close the dialog on success).
//
// A top-up has two answers (R10 Stage C5, F-5): a checkout to open, or an
// ACCEPTED request — the workspace has no Stripe connector, so the request
// was recorded and handed to the tenant to settle out of band. The second
// opens nothing. Its `status` is the registry's closed `top_up_request_status`,
// and this file is the console's declared consumer of that concept: the
// status is worded from the catalogue through its generated label keys, and
// the branch is decided by `../lib/top-up` against the generated value list —
// never a spelled-out token anywhere.

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros } from "@/lib/format";
import { labelMap } from "@/lib/localisation";
import { TOP_UP_REQUEST_STATUS_LABEL_KEYS } from "@/lib/vocabulary";

import { useTopUp, useWithdraw } from "../api/queries";
import type { BalanceResponse } from "../api/types";
import { toMicros } from "../lib/helpers";
import { isTopUpAccepted } from "../lib/top-up";
import {
  topUpSchema,
  withdrawSchema,
  type TopUpForm,
  type WithdrawForm,
} from "../lib/schemas";

/** The catalogue's words for an accepted top-up request's status. */
const topUpRequestStatusLabel = labelMap(TOP_UP_REQUEST_STATUS_LABEL_KEYS);

function useIdempotencyKey(open: boolean): string {
  const [key, setKey] = React.useState(() => crypto.randomUUID());
  React.useEffect(() => {
    if (open) setKey(crypto.randomUUID());
  }, [open]);
  return key;
}

export function TopUpDialog({
  customerId,
  open,
  onOpenChange,
}: {
  customerId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const currency = useTenantCurrency();
  const idempotencyKey = useIdempotencyKey(open);
  const mutation = useTopUp(customerId);
  const form = useForm<TopUpForm>({
    resolver: zodResolver(topUpSchema),
    defaultValues: { amount: "" },
  });

  const submit = form.handleSubmit(async (values) => {
    try {
      const result = await mutation.mutateAsync({
        amount_micros: toMicros(values.amount),
        success_url: window.location.href,
        cancel_url: window.location.href,
        idempotency_key: idempotencyKey,
      });
      if (isTopUpAccepted(result)) {
        // Nothing to open: the request is recorded and handed to the
        // workspace to settle; the wallet moves when it does.
        toast.success(topUpRequestStatusLabel(result.status), {
          description: result.message,
        });
      } else {
        window.open(result.checkout_url, "_blank", "noopener");
        toast.success("Stripe Checkout opened in a new tab");
      }
      form.reset();
      onOpenChange(false);
    } catch {
      // surfaced below; retry reuses the same idempotency key
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Top up balance</DialogTitle>
          <DialogDescription>
            Opens Stripe Checkout in a new tab; the wallet is credited when the
            payment completes. Where this workspace has no Stripe connector,
            the request is recorded for you to settle out of band instead, and
            nothing opens.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void submit(event)} className="space-y-3">
          <FormField
            label={`Amount (${currency.toUpperCase()})`}
            error={form.formState.errors.amount?.message}
            hint="Entered in currency units, e.g. 100 = one hundred."
          >
            {(id) => (
              <Input id={id} inputMode="decimal" {...form.register("amount")} autoFocus />
            )}
          </FormField>
          {mutation.error != null && (
            <p className="text-[12px] text-danger-dark" role="alert">
              {problemMessage(mutation.error)}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Working…" : "Start top-up"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function WithdrawDialog({
  customerId,
  balance,
  open,
  onOpenChange,
}: {
  customerId: string;
  balance: BalanceResponse | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const currency = useTenantCurrency();
  const idempotencyKey = useIdempotencyKey(open);
  const mutation = useWithdraw(customerId);
  const form = useForm<WithdrawForm>({
    resolver: zodResolver(withdrawSchema),
    defaultValues: { amount: "", description: "" },
  });

  const withdrawable =
    balance !== undefined
      ? balance.balance_micros - (balance.promo_micros ?? 0)
      : null;

  const submit = form.handleSubmit(async (values) => {
    try {
      const result = await mutation.mutateAsync({
        amount_micros: toMicros(values.amount),
        description: values.description,
        idempotency_key: idempotencyKey,
      });
      toast.success(
        `Withdrawal recorded — balance is now ${formatMicros(result.balance_micros, currency)}`,
      );
      form.reset();
      onOpenChange(false);
    } catch {
      // surfaced below
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Withdraw</DialogTitle>
          <DialogDescription>
            Withdraws base and paid credit. Promo credit is not withdrawable
            {withdrawable !== null && (
              <> — withdrawable now: {formatMicros(Math.max(withdrawable, 0), currency)}</>
            )}
            .
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void submit(event)} className="space-y-3">
          <FormField
            label={`Amount (${currency.toUpperCase()})`}
            error={form.formState.errors.amount?.message}
          >
            {(id) => (
              <Input id={id} inputMode="decimal" {...form.register("amount")} autoFocus />
            )}
          </FormField>
          <FormField label="Description" hint="Optional note on the ledger entry.">
            {(id) => <Input id={id} {...form.register("description")} />}
          </FormField>
          {mutation.error != null && (
            <p className="text-[12px] text-danger-dark" role="alert">
              {problemMessage(mutation.error)}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Working…" : "Withdraw"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
