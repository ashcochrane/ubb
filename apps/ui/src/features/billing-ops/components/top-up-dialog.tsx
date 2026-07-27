import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { useCreateTopUp } from "../api/queries";
import { topUpSchema, type TopUpFormValues } from "../lib/schema";

/**
 * Starts a prepaid top-up. The backend returns a Stripe Checkout URL; we send
 * the admin there to complete payment.
 */
export function TopUpDialog({ customerId }: { customerId: string }) {
  const [open, setOpen] = useState(false);
  const topUp = useCreateTopUp(customerId);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<TopUpFormValues>({
    resolver: zodResolver(topUpSchema),
    defaultValues: { amount: 0 },
  });

  async function onSubmit(values: TopUpFormValues) {
    const here = `${window.location.origin}${window.location.pathname}`;
    const { checkout_url } = await topUp.mutateAsync({
      amount_micros: Math.round(values.amount * 1_000_000),
      success_url: `${here}?topup=success`,
      cancel_url: `${here}?topup=cancel`,
      idempotency_key: crypto.randomUUID(),
    });
    setOpen(false);
    reset();
    if (checkout_url) window.location.assign(checkout_url);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>Top up</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Top up wallet</DialogTitle>
          <DialogDescription>
            You'll be redirected to Stripe Checkout to complete payment.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <FormField label="Amount (USD)" error={errors.amount?.message}>
            {(id) => (
              <Input id={id} type="number" min={1} step={1} {...register("amount", { valueAsNumber: true })} />
            )}
          </FormField>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={topUp.isPending}>
              {topUp.isPending ? "Starting…" : "Continue to payment"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
