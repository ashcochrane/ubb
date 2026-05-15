import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
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
import { useCreateCustomer } from "../api/queries";
import {
  customerCreateSchema,
  type CustomerCreateFormValues,
} from "../lib/schema";

export function CustomerCreateDialog() {
  const [open, setOpen] = useState(false);
  const create = useCreateCustomer();
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CustomerCreateFormValues>({
    resolver: zodResolver(customerCreateSchema),
    defaultValues: { externalId: "", stripeCustomerId: "" },
  });

  async function onSubmit(values: CustomerCreateFormValues) {
    const created = await create.mutateAsync({
      externalId: values.externalId,
      stripeCustomerId: values.stripeCustomerId,
      metadata: {},
    });
    setOpen(false);
    reset();
    navigate({
      to: "/customers/$customerId",
      params: { customerId: created.id },
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>New customer</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New customer</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <FormField label="External ID" error={errors.externalId?.message}>
            {(id) => (
              <Input
                id={id}
                placeholder="customer identifier you send from your app"
                {...register("externalId")}
              />
            )}
          </FormField>
          <FormField
            label="Stripe customer ID (optional)"
            error={errors.stripeCustomerId?.message}
          >
            {(id) => (
              <Input id={id} placeholder="cus_…" {...register("stripeCustomerId")} />
            )}
          </FormField>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
