import { useState } from "react";
import { useForm } from "react-hook-form";
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
import { useWithdraw } from "../api/queries";
import { withdrawSchema, type WithdrawFormValues } from "../lib/schema";

export function WithdrawDialog({ customerId }: { customerId: string }) {
  const [open, setOpen] = useState(false);
  const withdraw = useWithdraw(customerId);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<WithdrawFormValues>({
    resolver: zodResolver(withdrawSchema),
    defaultValues: { amount: 0, description: "" },
  });

  async function onSubmit(values: WithdrawFormValues) {
    await withdraw.mutateAsync({
      amount_micros: Math.round(values.amount * 1_000_000),
      description: values.description,
      idempotency_key: crypto.randomUUID(),
    });
    setOpen(false);
    reset();
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>Withdraw</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Withdraw from wallet</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <FormField label="Amount (USD)" error={errors.amount?.message}>
            {(id) => (
              <Input id={id} type="number" min={1} step={0.01} {...register("amount", { valueAsNumber: true })} />
            )}
          </FormField>
          <FormField label="Description" error={errors.description?.message}>
            {(id) => <Input id={id} placeholder="Reason for withdrawal" {...register("description")} />}
          </FormField>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={withdraw.isPending}>
              {withdraw.isPending ? "Withdrawing…" : "Withdraw"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
