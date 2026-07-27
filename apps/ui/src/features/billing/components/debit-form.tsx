import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros } from "@/lib/format";
import { toastSuccess } from "@/lib/mutations";

import { useDebitWallet } from "../api/queries";
import {
  currencyToMicros,
  debitFormSchema,
  type DebitFormValues,
} from "../lib/billing-forms";
import {
  AdjustmentSharedFields,
  LastResultLine,
  OptionalFields,
} from "./adjustment-shared";
import { useConfirmedAdjustment } from "../lib/use-confirmed-adjustment";

export function DebitForm({ isAdmin }: { isAdmin: boolean }) {
  const currency = useTenantCurrency();
  const mutation = useDebitWallet();
  const confirm = useConfirmedAdjustment();
  const form = useForm<DebitFormValues>({
    resolver: zodResolver(debitFormSchema),
    defaultValues: {
      customer_id: "",
      amount: "",
      reference: "",
      actor: "",
      reason_code: "",
      allow_negative: false,
    },
  });
  const values = form.getValues();

  const submitConfirmed = () => {
    const v = form.getValues();
    mutation.mutate(
      {
        customer_id: v.customer_id.trim(),
        amount_micros: currencyToMicros(v.amount),
        idempotency_key: confirm.idempotencyKey.current ?? crypto.randomUUID(),
        reference: v.reference.trim(),
        actor: v.actor.trim(),
        reason_code: v.reason_code.trim(),
        allow_negative: v.allow_negative,
      },
      {
        onSuccess: (result) => {
          confirm.onSuccessReset();
          confirm.setLastResult({ ...result, external_id: v.customer_id.trim() });
          toastSuccess(
            `Debited ${formatMicros(currencyToMicros(v.amount), currency)}`,
            `New balance: ${formatMicros(result.new_balance_micros, currency)}`,
          );
          form.reset();
        },
        onError: () => confirm.setConfirmOpen(false),
      },
    );
  };

  return (
    <form
      onSubmit={(e) => void form.handleSubmit(() => confirm.openConfirm())(e)}
      noValidate
      className="space-y-3"
    >
      <h3 className="text-[13px] font-semibold text-text-primary">Debit a wallet</h3>
      <p className="text-[12px] text-text-secondary">
        Removes money from the customer's balance — for corrections or clawing back a
        mistaken credit.
      </p>
      <AdjustmentSharedFields
        currency={currency}
        isAdmin={isAdmin}
        customer={form.register("customer_id")}
        amount={form.register("amount")}
        reference={form.register("reference")}
        errors={{
          customer: form.formState.errors.customer_id?.message,
          amount: form.formState.errors.amount?.message,
          reference: form.formState.errors.reference?.message,
        }}
      />
      <OptionalFields
        isAdmin={isAdmin}
        actor={form.register("actor")}
        reasonCode={form.register("reason_code")}
        errors={{
          actor: form.formState.errors.actor?.message,
          reasonCode: form.formState.errors.reason_code?.message,
        }}
      />
      <Controller
        control={form.control}
        name="allow_negative"
        render={({ field }) => (
          <label className="flex items-start gap-2.5">
            <Checkbox
              checked={field.value}
              onCheckedChange={(checked) => field.onChange(checked === true)}
              disabled={!isAdmin}
            />
            <span className="text-[12px]">
              <span className="font-medium text-text-primary">Allow a negative balance</span>
              <span className="mt-0.5 block text-text-secondary">
                Lets this debit push the balance below zero — the customer would owe the
                difference. Without it, a debit larger than the balance is refused.
              </span>
            </span>
          </label>
        )}
      />
      <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
        <Button type="submit" variant="destructive" disabled={!isAdmin || mutation.isPending}>
          {mutation.isPending ? "Working…" : "Debit…"}
        </Button>
      </DisabledHint>
      {mutation.isError && (
        <p className="text-xs text-destructive">{problemMessage(mutation.error)}</p>
      )}
      <LastResultLine result={confirm.lastResult} currency={currency} />
      <ConfirmDialog
        open={confirm.confirmOpen}
        onOpenChange={confirm.setConfirmOpen}
        title="Debit this wallet?"
        description={`Take ${formatMicros(currencyToMicros(values.amount || "0"), currency)} from ${
          values.customer_id.trim() || "this customer"
        }${values.allow_negative ? " — their balance is allowed to go negative" : ""}. Real money moves when you confirm.`}
        confirmLabel="Debit wallet"
        destructive
        onConfirm={submitConfirmed}
        pending={mutation.isPending}
      />
    </form>
  );
}
