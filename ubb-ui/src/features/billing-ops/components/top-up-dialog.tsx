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
import { useCreateTopUp } from "../api/queries";
import { topUpSchema, type TopUpFormValues } from "../lib/schema";

export function TopUpDialog({ customerId }: { customerId: string }) {
  const [open, setOpen] = useState(false);
  const topUp = useCreateTopUp(customerId);
  const { register, handleSubmit, reset, formState: { errors } } =
    useForm<TopUpFormValues>({
      resolver: zodResolver(topUpSchema),
      defaultValues: { amount: 0 },
    });

  async function onSubmit(values: TopUpFormValues) {
    const here = `${window.location.origin}${window.location.pathname}`;
    await topUp.mutateAsync({
      amountMicros: Math.round(values.amount * 1_000_000),
      successUrl: `${here}?topup=success`,
      cancelUrl: `${here}?topup=cancel`,
    });
    setOpen(false);
    reset();
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>Top up</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Top up wallet</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <FormField label="Amount (USD)" error={errors.amount?.message}>
            {(id) => (
              <Input
                id={id}
                type="number"
                min={1}
                step={1}
                {...register("amount", { valueAsNumber: true })}
              />
            )}
          </FormField>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={topUp.isPending}>
              {topUp.isPending ? "Starting…" : "Start top-up"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
