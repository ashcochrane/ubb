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
import { useCredit } from "../api/queries";
import { creditSchema, type CreditFormValues } from "../lib/schema";

/** Issue credit — adds funds to a customer's wallet. */
export function CreditDialog() {
  const [open, setOpen] = useState(false);
  const credit = useCredit();
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isValid },
  } = useForm<CreditFormValues>({
    resolver: zodResolver(creditSchema),
    mode: "onChange",
    defaultValues: {
      customerId: "",
      amount: 0,
      source: "",
      reference: "",
      reasonCode: "",
      actor: "",
    },
  });

  const submit = handleSubmit(async (v) => {
    await credit.mutateAsync({
      customer_id: v.customerId,
      amount_micros: Math.round(v.amount * 1_000_000),
      source: v.source,
      reference: v.reference,
      idempotency_key: crypto.randomUUID(),
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
      <DialogTrigger render={<Button size="sm" />}>Issue credit</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Issue credit</DialogTitle>
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
              label="Source"
              error={errors.source?.message}
              hint="Where the credit originates (e.g. goodwill, promo)."
            >
              {(id) => <Input id={id} {...register("source")} />}
            </FormField>
          </div>
          <FormField
            label="Reference"
            error={errors.reference?.message}
            hint="A traceable reference for this adjustment."
          >
            {(id) => <Input id={id} {...register("reference")} />}
          </FormField>
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
            trigger={<Button disabled={!isValid || credit.isPending}>Issue credit</Button>}
            title="Issue this credit?"
            description={`This moves money: it adds ${formatMicros(
              Math.round(amount * 1_000_000),
            )} to ${customerId || "the customer"}'s wallet balance. This cannot be undone here.`}
            confirmLabel="Issue credit"
            onConfirm={submit}
          />
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
