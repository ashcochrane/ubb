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
import { rotateSecretSchema, type RotateSecretValues } from "../lib/schema";
import { useRotateSecret } from "../api/queries";

/**
 * Rotate the signing secret. The old secret keeps verifying for `overlap_hours`
 * so in-flight consumers don't break — communicate that clearly.
 */
export function RotateSecretDialog({
  configId,
  trigger,
}: {
  configId: string;
  trigger: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const rotate = useRotateSecret(configId);
  const form = useForm<RotateSecretValues>({
    resolver: zodResolver(rotateSecretSchema),
    defaultValues: { new_secret: "", overlap_hours: 24 },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    await rotate.mutateAsync(values);
    setOpen(false);
    form.reset({ new_secret: "", overlap_hours: 24 });
  });

  const { errors } = form.formState;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Rotate signing secret</DialogTitle>
            <DialogDescription>
              The current secret keeps verifying deliveries during the overlap
              window, then retires. Update your consumer before it expires.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-4 flex flex-col gap-4">
            <FormField label="New signing secret" error={errors.new_secret?.message}>
              {(id) => (
                <Input id={id} type="password" autoComplete="off" placeholder="whsec_…" {...form.register("new_secret")} />
              )}
            </FormField>
            <FormField
              label="Overlap window (hours)"
              error={errors.overlap_hours?.message}
              hint="How long the old secret keeps working. 0 = retire immediately."
            >
              {(id) => (
                <Input
                  id={id}
                  type="number"
                  min={0}
                  max={168}
                  {...form.register("overlap_hours", { valueAsNumber: true })}
                />
              )}
            </FormField>
          </div>

          <DialogFooter className="mt-2">
            <DialogClose render={<Button variant="outline" type="button" disabled={rotate.isPending} />}>
              Cancel
            </DialogClose>
            <Button type="submit" disabled={rotate.isPending}>
              {rotate.isPending ? "Rotating…" : "Rotate secret"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
