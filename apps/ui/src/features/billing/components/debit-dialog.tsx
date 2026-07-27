import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { formatMicros } from "@/lib/format";
import { useDebit } from "../api/queries";
import { debitSchema, type DebitFormValues } from "../lib/schema";

/** Record debit — removes funds from a customer's wallet. */
export function DebitDialog() {
  const [open, setOpen] = useState(false);
  const debit = useDebit();
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isValid },
  } = useForm<DebitFormValues>({
    resolver: zodResolver(debitSchema),
    mode: "onChange",
    defaultValues: {
      customerId: "",
      amount: 0,
      reference: "",
      allowNegative: false,
      reasonCode: "",
      actor: "",
    },
  });

  const submit = handleSubmit(async (v) => {
    await debit.mutateAsync({
      customer_id: v.customerId,
      amount_micros: Math.round(v.amount * 1_000_000),
      reference: v.reference,
      idempotency_key: crypto.randomUUID(),
      allow_negative: v.allowNegative,
      reason_code: v.reasonCode,
      actor: v.actor,
    });
    setOpen(false);
    reset();
  });

  const amount = useWatch({ control, name: "amount" }) || 0;
  const customerId = useWatch({ control, name: "customerId" });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        Record debit
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record debit</DialogTitle>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
          <FormField label="Customer ID" error={errors.customerId?.message}>
            {(id) => <Input id={id} {...register("customerId")} />}
          </FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Amount (USD)" error={errors.amount?.message}>
              {(id) => (
                <Input
                  id={id}
                  type="number"
                  min={0.01}
                  step={0.01}
                  {...register("amount", { valueAsNumber: true })}
                />
              )}
            </FormField>
            <FormField
              label="Reference"
              error={errors.reference?.message}
              hint="A traceable reference for this adjustment."
            >
              {(id) => <Input id={id} {...register("reference")} />}
            </FormField>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-foreground"
              {...register("allowNegative")}
            />
            Allow the balance to go negative
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Reason code (optional)">
              {(id) => <Input id={id} {...register("reasonCode")} />}
            </FormField>
            <FormField label="Actor (optional)">
              {(id) => <Input id={id} {...register("actor")} />}
            </FormField>
          </div>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <ConfirmDialog
            trigger={
              <Button variant="destructive" disabled={!isValid || debit.isPending}>
                Record debit
              </Button>
            }
            title="Record this debit?"
            description={`This moves money: it removes ${formatMicros(
              Math.round(amount * 1_000_000),
            )} from ${customerId || "the customer"}'s wallet balance. This cannot be undone here.`}
            confirmLabel="Record debit"
            destructive
            onConfirm={submit}
          />
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
