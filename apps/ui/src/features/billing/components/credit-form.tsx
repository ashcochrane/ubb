import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros } from "@/lib/format";
import { toastSuccess } from "@/lib/mutations";

import { useCreditWallet } from "../api/queries";
import {
  creditFormSchema,
  currencyToMicros,
  type CreditFormValues,
} from "../lib/billing-forms";
import {
  AdjustmentSharedFields,
  LastResultLine,
  OptionalFields,
} from "./adjustment-shared";
import { useConfirmedAdjustment } from "../lib/use-confirmed-adjustment";

export function CreditForm({ isAdmin }: { isAdmin: boolean }) {
  const currency = useTenantCurrency();
  const mutation = useCreditWallet();
  const confirm = useConfirmedAdjustment();
  const form = useForm<CreditFormValues>({
    resolver: zodResolver(creditFormSchema),
    defaultValues: {
      customer_id: "",
      amount: "",
      reference: "",
      source: "",
      actor: "",
      reason_code: "",
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
        source: v.source.trim(),
        actor: v.actor.trim(),
        reason_code: v.reason_code.trim(),
      },
      {
        onSuccess: (result) => {
          confirm.onSuccessReset();
          confirm.setLastResult({ ...result, external_id: v.customer_id.trim() });
          toastSuccess(
            `Credited ${formatMicros(currencyToMicros(v.amount), currency)}`,
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
      <h3 className="text-[13px] font-semibold text-text-primary">Credit a wallet</h3>
      <p className="text-[12px] text-text-secondary">
        Adds non-expiring base credit. For expiring or promo credit, use a credit grant on
        the customer's page instead.
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
      <FormField
        label="Source"
        error={form.formState.errors.source?.message}
        hint="Where this credit comes from, e.g. support_goodwill."
      >
        {(id) => <Input id={id} {...form.register("source")} disabled={!isAdmin} />}
      </FormField>
      <OptionalFields
        isAdmin={isAdmin}
        actor={form.register("actor")}
        reasonCode={form.register("reason_code")}
        errors={{
          actor: form.formState.errors.actor?.message,
          reasonCode: form.formState.errors.reason_code?.message,
        }}
      />
      <Button type="submit" disabled={!isAdmin || mutation.isPending}>
        {mutation.isPending ? "Working…" : "Credit…"}
      </Button>
      {mutation.isError && (
        <p className="text-xs text-destructive">{problemMessage(mutation.error)}</p>
      )}
      <LastResultLine result={confirm.lastResult} currency={currency} />
      <ConfirmDialog
        open={confirm.confirmOpen}
        onOpenChange={confirm.setConfirmOpen}
        title="Credit this wallet?"
        description={`Credit ${values.customer_id.trim() || "this customer"} with ${formatMicros(
          currencyToMicros(values.amount || "0"),
          currency,
        )}. This immediately increases their spendable balance — real money moves when you confirm.`}
        confirmLabel="Credit wallet"
        onConfirm={submitConfirmed}
        pending={mutation.isPending}
      />
    </form>
  );
}
