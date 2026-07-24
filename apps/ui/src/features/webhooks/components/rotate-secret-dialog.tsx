import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { TriangleAlert } from "lucide-react";

import { problemMessage } from "@/api/problem";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { Label } from "@/components/ui/label";
import { formatDate } from "@/lib/format";
import { toastSuccess } from "@/lib/mutations";

import { useRotateWebhookSecret } from "../api/queries";
import { rotateSecretSchema, type RotateSecretValues } from "../lib/schemas";
import { SecretInput } from "./secret-input";
import { SecretReveal } from "./secret-reveal";

const DEFAULTS: RotateSecretValues = { newSecret: "", overlapHours: 24 };

/**
 * Two-secret overlap rotation: you supply a NEW secret; for the overlap
 * window both the new and the retiring secret sign every delivery, so a
 * receiver can switch over with zero downtime.
 */
export function RotateSecretDialog({
  configId,
  open,
  onOpenChange,
}: {
  configId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const rotate = useRotateWebhookSecret();
  const [result, setResult] = React.useState<{
    secret: string;
    expiresAt: string | null;
  } | null>(null);
  const overlapId = React.useId();

  const form = useForm<RotateSecretValues>({
    resolver: zodResolver(rotateSecretSchema),
    defaultValues: DEFAULTS,
  });
  const { errors, isSubmitted } = form.formState;
  const newSecret = form.watch("newSecret");

  const setOpen = (next: boolean) => {
    onOpenChange(next);
    if (!next) {
      form.reset(DEFAULTS);
      rotate.reset();
      setResult(null);
    }
  };

  const onSubmit = form.handleSubmit((values) => {
    rotate.mutate(
      {
        configId,
        body: { new_secret: values.newSecret, overlap_hours: values.overlapHours },
      },
      {
        onSuccess: (config) => {
          setResult({
            secret: values.newSecret,
            expiresAt: config.retiring_secret_expires_at ?? null,
          });
          toastSuccess("Secret rotated");
        },
      },
    );
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        {result ? (
          <div className="space-y-3">
            <DialogHeader>
              <DialogTitle>Secret rotated</DialogTitle>
              <DialogDescription>
                {result.expiresAt
                  ? `Deliveries are signed with BOTH secrets until ${formatDate(result.expiresAt)}. Update your receiver to the new secret before then.`
                  : "Deliveries are now signed with the new secret."}
              </DialogDescription>
            </DialogHeader>
            <SecretReveal
              secret={result.secret}
              context="This is the new secret you just supplied. UBB can never show it again — rotating again is the only way to replace it."
            />
            <DialogFooter>
              <Button onClick={() => setOpen(false)}>Done</Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={(event) => void onSubmit(event)} className="space-y-4">
            <DialogHeader>
              <DialogTitle>Rotate signing secret</DialogTitle>
              <DialogDescription>
                Supply a new secret. For the overlap window, every delivery is signed
                with both the new and the retiring secret, so your receiver verifies
                with zero downtime. Rotating again mid-window replaces the retiring
                secret.
              </DialogDescription>
            </DialogHeader>

            <SecretInput
              label="New signing secret"
              value={newSecret}
              onChange={(secret) =>
                form.setValue("newSecret", secret, { shouldValidate: isSubmitted })
              }
              error={errors.newSecret?.message}
            />

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={overlapId}>Overlap window (hours)</Label>
              <Input
                id={overlapId}
                type="number"
                min={1}
                max={168}
                className="w-32"
                {...form.register("overlapHours", { valueAsNumber: true })}
              />
              {errors.overlapHours ? (
                <p className="text-xs text-destructive">{errors.overlapHours.message}</p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  1–168 hours (up to 7 days). Both secrets sign during this window.
                </p>
              )}
            </div>

            {rotate.isError && (
              <Alert>
                <TriangleAlert aria-hidden="true" />
                <AlertTitle>Couldn't rotate the secret</AlertTitle>
                <AlertDescription>{problemMessage(rotate.error)}</AlertDescription>
              </Alert>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={rotate.isPending}>
                {rotate.isPending ? "Working…" : "Rotate secret"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
