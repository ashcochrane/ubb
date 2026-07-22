import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { attributeSchema, type AttributeValues } from "../lib/schema";
import { useAttributeReferral } from "../api/queries";

/**
 * Attribute a referred customer to a referrer using either the referral code
 * or the link token. At least one of the two is required.
 */
export function AttributeDialog({ trigger }: { trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  const attribute = useAttributeReferral();

  const form = useForm<AttributeValues>({
    resolver: zodResolver(attributeSchema),
    defaultValues: { customer_id: "", code: "", link_token: "" },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    await attribute.mutateAsync({
      customer_id: values.customer_id,
      code: values.code || undefined,
      link_token: values.link_token || undefined,
    });
    setOpen(false);
    form.reset({ customer_id: "", code: "", link_token: "" });
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) form.reset({ customer_id: "", code: "", link_token: "" });
      }}
    >
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Attribute referral</DialogTitle>
            <DialogDescription>
              Link a customer to the referrer who brought them in. Provide the
              referral code or the link token.
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 flex flex-col gap-4">
            <FormField label="Referred customer ID" error={errors.customer_id?.message}>
              {(id) => (
                <Input id={id} placeholder="cus_…" {...form.register("customer_id")} />
              )}
            </FormField>
            <FormField
              label="Referral code"
              error={errors.code?.message}
              hint="Enter this or the link token below."
            >
              {(id) => <Input id={id} {...form.register("code")} />}
            </FormField>
            <FormField label="Link token" error={errors.link_token?.message}>
              {(id) => <Input id={id} {...form.register("link_token")} />}
            </FormField>
          </div>
          <DialogFooter className="mt-2">
            <DialogClose
              render={
                <Button variant="outline" type="button" disabled={attribute.isPending} />
              }
            >
              Cancel
            </DialogClose>
            <Button type="submit" disabled={attribute.isPending}>
              {attribute.isPending ? "Attributing…" : "Attribute"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
