import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronDown, ChevronRight, Plus, X } from "lucide-react";
import { useFieldArray, useForm } from "react-hook-form";
import { toast } from "sonner";

import { ApiProblem, problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { useCreateCustomer } from "../api/queries";
import { createCustomerSchema, type CreateCustomerForm } from "../lib/schemas";

const DEFAULTS: CreateCustomerForm = {
  external_id: "",
  account_type: "individual",
  billing_topology: "",
  parent_external_id: "",
  stripe_customer_id: "",
  metadata: [],
};

export function CreateCustomerDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (customerId: string) => void;
}) {
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const mutation = useCreateCustomer();
  const form = useForm<CreateCustomerForm>({
    resolver: zodResolver(createCustomerSchema),
    defaultValues: DEFAULTS,
  });
  const metadata = useFieldArray({ control: form.control, name: "metadata" });
  const accountType = form.watch("account_type");

  const submit = form.handleSubmit(async (values) => {
    try {
      const created = await mutation.mutateAsync({
        external_id: values.external_id,
        account_type: values.account_type,
        billing_topology: values.billing_topology,
        parent_external_id: values.parent_external_id,
        stripe_customer_id: values.stripe_customer_id,
        metadata: Object.fromEntries(
          values.metadata
            .filter((pair) => pair.key.trim() !== "")
            .map((pair) => [pair.key.trim(), pair.value]),
        ),
      });
      toast.success(`Customer ${created.external_id} created`);
      form.reset(DEFAULTS);
      onOpenChange(false);
      onCreated(created.id);
    } catch {
      // Error surfaced below; user input is kept.
    }
  });

  const error = mutation.error;
  const isConflict = error instanceof ApiProblem && error.status === 409;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New customer</DialogTitle>
          <DialogDescription>
            Register a customer under your own identifier. Usage, billing, and
            margin all key off this record.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void submit(event)} className="space-y-3">
          <FormField
            label="External ID"
            error={form.formState.errors.external_id?.message}
            hint="Your system's identifier for this customer — used across the API."
          >
            {(id) => (
              <Input
                id={id}
                {...form.register("external_id")}
                placeholder="acme-corp"
                autoFocus
              />
            )}
          </FormField>
          <FormField
            label="Account type"
            hint='The API accepts other values too; "business" enables seats underneath.'
          >
            {() => (
              <Select
                value={accountType}
                onValueChange={(value) =>
                  form.setValue("account_type", value ?? "individual")
                }
              >
                <SelectTrigger className="w-full" aria-label="Account type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="individual">Individual</SelectItem>
                  <SelectItem value="business">Business</SelectItem>
                </SelectContent>
              </Select>
            )}
          </FormField>

          <button
            type="button"
            className="flex items-center gap-1 text-[12px] font-medium text-text-secondary hover:text-text-primary"
            onClick={() => setAdvancedOpen((current) => !current)}
          >
            {advancedOpen ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
            Advanced
          </button>

          {advancedOpen && (
            <div className="space-y-3 rounded-md border border-border bg-bg-subtle/40 p-3">
              <FormField
                label="Parent external ID"
                hint="Create this customer as a seat under an existing business (the parent's external ID)."
              >
                {(id) => (
                  <Input
                    id={id}
                    {...form.register("parent_external_id")}
                    placeholder="acme-corp"
                  />
                )}
              </FormField>
              <FormField
                label="Stripe customer ID"
                hint="Link an existing Stripe customer instead of creating one later."
              >
                {(id) => (
                  <Input
                    id={id}
                    {...form.register("stripe_customer_id")}
                    placeholder="cus_…"
                  />
                )}
              </FormField>
              <FormField
                label="Billing topology"
                hint='For businesses with seats: "pooled" — seats spend from the business
                  wallet — or "allocated" — each seat funds itself. Free-text; other
                  values are passed through as-is.'
              >
                {(id) => (
                  <Input
                    id={id}
                    {...form.register("billing_topology")}
                    placeholder="pooled"
                  />
                )}
              </FormField>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[12px] font-medium">Metadata</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    onClick={() => metadata.append({ key: "", value: "" })}
                  >
                    <Plus /> Add pair
                  </Button>
                </div>
                {metadata.fields.length === 0 && (
                  <p className="text-[11px] text-text-muted">
                    Optional key–value pairs stored on the customer.
                  </p>
                )}
                {metadata.fields.map((field, index) => (
                  <div key={field.id} className="flex items-center gap-1.5">
                    <Input
                      {...form.register(`metadata.${index}.key`)}
                      placeholder="key"
                      aria-label={`Metadata key ${index + 1}`}
                      className="h-7 font-mono text-[12px]"
                    />
                    <Input
                      {...form.register(`metadata.${index}.value`)}
                      placeholder="value"
                      aria-label={`Metadata value ${index + 1}`}
                      className="h-7 font-mono text-[12px]"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      aria-label={`Remove metadata pair ${index + 1}`}
                      onClick={() => metadata.remove(index)}
                    >
                      <X />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {error != null && (
            <p className="text-[12px] text-danger-dark" role="alert">
              {isConflict
                ? "A customer with this external ID already exists — pick another."
                : problemMessage(error)}
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
              {mutation.isPending ? "Working…" : "Create customer"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
