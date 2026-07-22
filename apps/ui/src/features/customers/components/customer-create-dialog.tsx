import { useState, type ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { useCreateCustomer } from "../api/queries";
import { customerCreateSchema, type CustomerCreateValues } from "../lib/schema";

export function CustomerCreateDialog({ trigger }: { trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const create = useCreateCustomer();
  const form = useForm<CustomerCreateValues>({
    resolver: zodResolver(customerCreateSchema),
    defaultValues: {
      external_id: "",
      stripe_customer_id: "",
      account_type: "individual",
      parent_external_id: "",
      billing_topology: "",
    },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    const created = await create.mutateAsync({
      external_id: values.external_id,
      stripe_customer_id: values.stripe_customer_id || "",
      account_type: values.account_type,
      parent_external_id: values.parent_external_id || "",
      billing_topology: values.billing_topology || "",
      metadata: {},
    });
    setOpen(false);
    form.reset();
    navigate({ to: "/customers/$customerId", params: { customerId: created.id } });
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent>
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>New customer</DialogTitle>
            <DialogDescription>
              Create a customer record. The external ID is how you'll reference this customer from your systems.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-4 flex flex-col gap-4">
            <FormField label="External ID" error={errors.external_id?.message}>
              {(id) => <Input id={id} placeholder="acme-inc" {...form.register("external_id")} />}
            </FormField>
            <FormField label="Account type" error={errors.account_type?.message}>
              {() => (
                <Controller
                  control={form.control}
                  name="account_type"
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="individual">Individual</SelectItem>
                        <SelectItem value="business">Business</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                />
              )}
            </FormField>
            <FormField
              label="Stripe customer ID"
              hint="Optional — link to an existing Stripe customer."
              error={errors.stripe_customer_id?.message}
            >
              {(id) => <Input id={id} placeholder="cus_…" {...form.register("stripe_customer_id")} />}
            </FormField>
            <FormField
              label="Parent external ID"
              hint="Optional — for a customer that rolls up to a parent account."
              error={errors.parent_external_id?.message}
            >
              {(id) => <Input id={id} placeholder="parent-account" {...form.register("parent_external_id")} />}
            </FormField>
          </div>

          <DialogFooter className="mt-2">
            <DialogClose render={<Button variant="outline" type="button" disabled={create.isPending} />}>
              Cancel
            </DialogClose>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create customer"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
