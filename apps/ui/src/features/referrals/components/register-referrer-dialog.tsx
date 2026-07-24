import { useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { toastSuccess } from "@/lib/mutations";

import { useMarginCustomerPicker, useRegisterReferrer } from "../api/queries";
import { registerReferrerSchema, type RegisterReferrerValues } from "../lib/schemas";

export function RegisterReferrerDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const form = useForm<RegisterReferrerValues>({
    resolver: zodResolver(registerReferrerSchema),
    defaultValues: { customer_id: "" },
  });
  const picker = useMarginCustomerPicker(open);
  const mutation = useRegisterReferrer();

  useEffect(() => {
    if (open) {
      form.reset({ customer_id: "" });
      mutation.reset();
    }
    // Reset only when the dialog (re)opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const submit = form.handleSubmit((values) =>
    mutation.mutate(values.customer_id, {
      onSuccess: (result) => {
        toastSuccess(
          "Referrer registered",
          `Share code ${result.referral_code} — or the referral link token.`,
        );
        onOpenChange(false);
      },
    }),
  );

  const pickerRows = picker.data ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Register a referrer</DialogTitle>
          <DialogDescription>
            Turns an existing customer into a referrer with a shareable code and link token.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4" noValidate>
          {pickerRows.length > 0 && (
            <FormField
              label="Pick a customer"
              hint="Recent customers from margin reporting — or paste any UBB customer UUID below."
            >
              {(id) => (
                <Select
                  onValueChange={(value) => {
                    if (typeof value === "string") {
                      form.setValue("customer_id", value, { shouldValidate: true });
                    }
                  }}
                >
                  <SelectTrigger id={id} className="w-full">
                    <span className="truncate font-mono text-[12px] text-muted-foreground">
                      {form.watch("customer_id") || "Choose a customer…"}
                    </span>
                  </SelectTrigger>
                  <SelectContent>
                    {pickerRows.map((row) => (
                      <SelectItem key={row.customer_id} value={row.customer_id}>
                        <span className="font-mono text-[12px]">{row.customer_id}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </FormField>
          )}
          <FormField
            label="Customer UUID"
            error={form.formState.errors.customer_id?.message}
            hint="The UBB customer UUID — not your own external customer ID."
          >
            {(id) => (
              <Input
                id={id}
                className="font-mono"
                placeholder="9f1c2e34-…"
                autoComplete="off"
                {...form.register("customer_id")}
              />
            )}
          </FormField>
          {mutation.error ? (
            <p className="text-xs text-destructive">{problemMessage(mutation.error)}</p>
          ) : null}
          <div className="flex justify-end">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Working…" : "Register"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
