import { useState, type ReactNode } from "react";
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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { CopyField } from "@/components/shared/data-states";
import { EventTypesInput } from "./event-types-input";
import { webhookCreateSchema, type WebhookCreateValues } from "../lib/schema";
import { useCreateWebhook, useUpdateWebhook } from "../api/queries";
import type { WebhookConfig } from "../api/types";

/**
 * Create or edit a webhook endpoint. On create, the signing secret is entered
 * by the tenant and never returned by the API — so once created we surface it
 * one last time with a copy affordance and a clear "won't be shown again" note.
 */
export function WebhookFormDialog({
  trigger,
  existing,
}: {
  trigger: ReactNode;
  existing?: WebhookConfig;
}) {
  const isEdit = Boolean(existing);
  const [open, setOpen] = useState(false);
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);

  const create = useCreateWebhook();
  const update = useUpdateWebhook(existing?.id ?? "");

  const form = useForm<WebhookCreateValues>({
    resolver: zodResolver(webhookCreateSchema),
    defaultValues: {
      url: existing?.url ?? "",
      secret: "",
      event_types: existing?.event_types ?? [],
      is_active: existing?.is_active ?? true,
    },
  });

  const reset = () => {
    form.reset({
      url: existing?.url ?? "",
      secret: "",
      event_types: existing?.event_types ?? [],
      is_active: existing?.is_active ?? true,
    });
    setCreatedSecret(null);
  };

  const onSubmit = form.handleSubmit(async (values) => {
    if (isEdit && existing) {
      await update.mutateAsync({
        url: values.url,
        event_types: values.event_types,
        is_active: values.is_active,
      });
      setOpen(false);
    } else {
      await create.mutateAsync({
        url: values.url,
        secret: values.secret,
        event_types: values.event_types,
        is_active: values.is_active,
      });
      setCreatedSecret(values.secret);
    }
  });

  const pending = create.isPending || update.isPending;
  const { errors } = form.formState;

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
        {createdSecret ? (
          <>
            <DialogHeader>
              <DialogTitle>Endpoint created</DialogTitle>
              <DialogDescription>
                Store this signing secret securely — it verifies the HMAC
                signature on every delivery and won't be shown again.
              </DialogDescription>
            </DialogHeader>
            <CopyField label="Signing secret" value={createdSecret} />
            <DialogFooter>
              <DialogClose render={<Button />}>Done</DialogClose>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={onSubmit}>
            <DialogHeader>
              <DialogTitle>{isEdit ? "Edit endpoint" : "New webhook endpoint"}</DialogTitle>
              <DialogDescription>
                Deliveries are POSTed to your URL and signed with HMAC-SHA256.
              </DialogDescription>
            </DialogHeader>

            <div className="mt-4 flex flex-col gap-4">
              <FormField label="Endpoint URL" error={errors.url?.message}>
                {(id) => (
                  <Input id={id} placeholder="https://api.example.com/hooks/ubb" {...form.register("url")} />
                )}
              </FormField>

              {!isEdit && (
                <FormField
                  label="Signing secret"
                  error={errors.secret?.message}
                  hint="Used to sign deliveries. Keep it secret; you can rotate it later."
                >
                  {(id) => (
                    <Input id={id} type="password" autoComplete="off" placeholder="whsec_…" {...form.register("secret")} />
                  )}
                </FormField>
              )}

              <FormField label="Event types" error={errors.event_types?.message as string | undefined}>
                {() => (
                  <Controller
                    control={form.control}
                    name="event_types"
                    render={({ field }) => (
                      <EventTypesInput
                        value={field.value}
                        onChange={field.onChange}
                        invalid={Boolean(errors.event_types)}
                      />
                    )}
                  />
                )}
              </FormField>

              <Controller
                control={form.control}
                name="is_active"
                render={({ field }) => (
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={field.value}
                      onChange={(e) => field.onChange(e.target.checked)}
                      className="size-4 accent-foreground"
                    />
                    Active — deliver events immediately
                  </label>
                )}
              />
            </div>

            <DialogFooter className="mt-2">
              <DialogClose render={<Button variant="outline" type="button" disabled={pending} />}>
                Cancel
              </DialogClose>
              <Button type="submit" disabled={pending}>
                {pending ? "Saving…" : isEdit ? "Save changes" : "Create endpoint"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
