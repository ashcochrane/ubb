// Manual credit / debit (which take the EXTERNAL id in the body — prefilled
// and shown read-only here) and the pre-check dialog (denials are HTTP 200
// with allowed:false — the UI branches on the body, never the status).
//
// Money moves on these forms, so submit goes through a ConfirmDialog with
// the same consequence copy as the /billing page's credit/debit forms. The
// idempotency key is minted per dialog-open and REUSED across the confirm
// step and any retry after failure (replay-safe).

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, XCircle } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { problemMessage } from "@/api/problem";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros } from "@/lib/format";
import { preCheckReasonLabel } from "@/lib/labels";

import { useCreditWallet, useDebitWallet, usePreCheck } from "../api/queries";
import { toMicros } from "../lib/helpers";
import { adjustSchema, type AdjustForm } from "../lib/schemas";

function useIdempotencyKey(open: boolean): string {
  const [key, setKey] = React.useState(() => crypto.randomUUID());
  React.useEffect(() => {
    if (open) setKey(crypto.randomUUID());
  }, [open]);
  return key;
}

export function AdjustDialog({
  direction,
  externalId,
  open,
  onOpenChange,
}: {
  direction: "credit" | "debit";
  externalId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const currency = useTenantCurrency();
  const idempotencyKey = useIdempotencyKey(open);
  const credit = useCreditWallet();
  const debit = useDebitWallet();
  const isCredit = direction === "credit";
  const mutation = isCredit ? credit : debit;

  const form = useForm<AdjustForm>({
    resolver: zodResolver(adjustSchema(direction)),
    defaultValues: {
      amount: "",
      reference: "",
      source: isCredit ? "console" : "",
      reason_code: "",
      allow_negative: false,
    },
  });
  const allowNegative = form.watch("allow_negative");
  const amount = form.watch("amount");
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  // Valid form → confirm step; money only moves from the ConfirmDialog.
  const submit = form.handleSubmit(() => setConfirmOpen(true));

  const submitConfirmed = async () => {
    const values = form.getValues();
    try {
      const result = isCredit
        ? await credit.mutateAsync({
            customer_id: externalId,
            amount_micros: toMicros(values.amount),
            idempotency_key: idempotencyKey,
            reference: values.reference,
            source: values.source,
            actor: "",
            reason_code: values.reason_code,
          })
        : await debit.mutateAsync({
            customer_id: externalId,
            amount_micros: toMicros(values.amount),
            idempotency_key: idempotencyKey,
            reference: values.reference,
            actor: "",
            reason_code: values.reason_code,
            allow_negative: values.allow_negative,
          });
      setConfirmOpen(false);
      toast.success(
        `${isCredit ? "Credited" : "Debited"} — new balance ${formatMicros(result.new_balance_micros, currency)}`,
      );
      form.reset();
      onOpenChange(false);
    } catch {
      // Surfaced below in the form dialog; a retry through the same confirm
      // reuses the idempotency key (replay-safe).
      setConfirmOpen(false);
    }
  };

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{isCredit ? "Manual credit" : "Manual debit"}</DialogTitle>
          <DialogDescription>
            {isCredit
              ? "Adds non-expiring base credit (no grant lot). Use a credit grant instead for promo or expiring credit."
              : "Removes money from the wallet, recorded as a debit on the wallet ledger."}{" "}
            This endpoint identifies the customer by external ID.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void submit(event)} className="space-y-3">
          <FormField label="Customer (external ID)">
            {(id) => <Input id={id} value={externalId} readOnly className="font-mono" />}
          </FormField>
          <FormField
            label={`Amount (${currency.toUpperCase()})`}
            error={form.formState.errors.amount?.message}
          >
            {(id) => (
              <Input id={id} inputMode="decimal" {...form.register("amount")} autoFocus />
            )}
          </FormField>
          <FormField
            label="Reference"
            error={form.formState.errors.reference?.message}
            hint="What this adjustment is for — lands on the ledger entry."
          >
            {(id) => <Input id={id} {...form.register("reference")} />}
          </FormField>
          {isCredit && (
            <FormField
              label="Source"
              error={form.formState.errors.source?.message}
              hint='Where the money movement originated, e.g. "console" or "support".'
            >
              {(id) => <Input id={id} {...form.register("source")} />}
            </FormField>
          )}
          <FormField
            label="Reason code"
            error={form.formState.errors.reason_code?.message}
            hint="Optional short machine code (32 chars max)."
          >
            {(id) => <Input id={id} {...form.register("reason_code")} />}
          </FormField>
          {!isCredit && (
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="allow-negative"
                  checked={allowNegative}
                  onCheckedChange={(checked) =>
                    form.setValue("allow_negative", checked === true)
                  }
                />
                <Label htmlFor="allow-negative">Allow the balance to go negative</Label>
              </div>
              {allowNegative && (
                <p className="text-[11px] text-danger-dark">
                  The wallet can end below zero — spend gating will trip and the
                  balance will show as negative until it's repaid.
                </p>
              )}
            </div>
          )}
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
              {mutation.isPending ? "Working…" : isCredit ? "Credit…" : "Debit…"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
    <ConfirmDialog
      open={confirmOpen}
      onOpenChange={setConfirmOpen}
      title={isCredit ? "Credit this wallet?" : "Debit this wallet?"}
      destructive={!isCredit}
      description={
        isCredit
          ? `Credit ${externalId} with ${formatMicros(toMicros(amount || "0"), currency)}. This immediately increases their spendable balance — real money moves when you confirm.`
          : `Take ${formatMicros(toMicros(amount || "0"), currency)} from ${externalId}${allowNegative ? " — their balance is allowed to go negative" : ""}. Real money moves when you confirm.`
      }
      confirmLabel={isCredit ? "Credit wallet" : "Debit wallet"}
      onConfirm={() => void submitConfirmed()}
      pending={mutation.isPending}
    />
    </>
  );
}

export function PreCheckDialog({
  customerId,
  open,
  onOpenChange,
}: {
  customerId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const currency = useTenantCurrency();
  const mutation = usePreCheck(customerId);
  const result = mutation.data;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) mutation.reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Run access check</DialogTitle>
          <DialogDescription>
            The same pre-start check your agents call before spending: suspension,
            stop flags, balance floors, budget, and rate limits. It changes
            nothing — a denial is a normal answer, not an error.
          </DialogDescription>
        </DialogHeader>
        {result && (
          <div
            className="flex items-start gap-2 rounded-md border border-border bg-bg-subtle/50 p-3"
            role="status"
          >
            {result.allowed ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
            ) : (
              <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger-dark" />
            )}
            <div className="text-[13px]">
              <div className="font-medium">
                {result.allowed ? "Allowed — this customer can spend" : "Denied"}
              </div>
              {!result.allowed && (
                <div className="text-text-secondary">
                  Reason: {preCheckReasonLabel(result.reason)}
                </div>
              )}
              {typeof result.balance_micros === "number" && (
                <div className="text-text-secondary">
                  Balance at check: {formatMicros(result.balance_micros, currency)}
                </div>
              )}
            </div>
          </div>
        )}
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
            Close
          </Button>
          <Button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Working…" : result ? "Run again" : "Run check"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
