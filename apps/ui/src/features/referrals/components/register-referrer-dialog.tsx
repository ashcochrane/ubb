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
import { CopyField } from "@/components/shared/data-states";
import {
  registerReferrerSchema,
  type RegisterReferrerValues,
} from "../lib/schema";
import { useRegisterReferrer } from "../api/queries";
import type { Referrer } from "../api/types";

/**
 * Register an existing customer as a referrer. On success we surface the
 * generated referral code and link token so they can be shared immediately.
 */
export function RegisterReferrerDialog({ trigger }: { trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<Referrer | null>(null);
  const register = useRegisterReferrer();

  const form = useForm<RegisterReferrerValues>({
    resolver: zodResolver(registerReferrerSchema),
    defaultValues: { customer_id: "" },
  });

  const reset = () => {
    form.reset({ customer_id: "" });
    setCreated(null);
  };

  const onSubmit = form.handleSubmit(async (values) => {
    const referrer = await register.mutateAsync(values);
    setCreated(referrer);
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) reset();
      }}
    >
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent className="sm:max-w-md">
        {created ? (
          <>
            <DialogHeader>
              <DialogTitle>Referrer registered</DialogTitle>
              <DialogDescription>
                Share this code or link so referred customers can be attributed.
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-3">
              <CopyField label="Referral code" value={created.referral_code} />
              <CopyField
                label="Referral link token"
                value={created.referral_link_token}
              />
            </div>
            <DialogFooter>
              <DialogClose render={<Button />}>Done</DialogClose>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={onSubmit}>
            <DialogHeader>
              <DialogTitle>Register referrer</DialogTitle>
              <DialogDescription>
                Enrol an existing customer so they can refer others and earn rewards.
              </DialogDescription>
            </DialogHeader>
            <div className="mt-4">
              <FormField
                label="Customer ID"
                error={form.formState.errors.customer_id?.message}
              >
                {(id) => (
                  <Input id={id} placeholder="cus_…" {...form.register("customer_id")} />
                )}
              </FormField>
            </div>
            <DialogFooter className="mt-2">
              <DialogClose
                render={
                  <Button
                    variant="outline"
                    type="button"
                    disabled={register.isPending}
                  />
                }
              >
                Cancel
              </DialogClose>
              <Button type="submit" disabled={register.isPending}>
                {register.isPending ? "Registering…" : "Register"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
