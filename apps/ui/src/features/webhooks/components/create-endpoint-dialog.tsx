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
import { Switch } from "@/components/ui/switch";
import { toastSuccess } from "@/lib/mutations";

import { useCreateWebhookConfig } from "../api/queries";
import {
  createEndpointSchema,
  toEventTypesPayload,
  type CreateEndpointValues,
} from "../lib/schemas";
import { EventTypePicker } from "./event-type-picker";
import { SecretInput } from "./secret-input";
import { SecretReveal } from "./secret-reveal";

const DEFAULTS: CreateEndpointValues = {
  url: "",
  secret: "",
  // Default to the wildcard: most integrations start by receiving everything
  // and narrow later — and the 35-type catalog only renders when narrowing.
  allEvents: true,
  eventTypes: [],
  isActive: true,
};

export function CreateEndpointDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const create = useCreateWebhookConfig();
  const [created, setCreated] = React.useState<{ url: string; secret: string } | null>(
    null,
  );
  const activeId = React.useId();

  const form = useForm<CreateEndpointValues>({
    resolver: zodResolver(createEndpointSchema),
    defaultValues: DEFAULTS,
  });
  const { errors, isSubmitted } = form.formState;
  const values = form.watch();

  const setOpen = (next: boolean) => {
    onOpenChange(next);
    if (!next) {
      form.reset(DEFAULTS);
      create.reset();
      setCreated(null);
    }
  };

  const onSubmit = form.handleSubmit((formValues) => {
    create.mutate(
      {
        url: formValues.url,
        secret: formValues.secret,
        event_types: toEventTypesPayload(formValues),
        is_active: formValues.isActive,
      },
      {
        onSuccess: (config) => {
          setCreated({ url: config.url, secret: formValues.secret });
          toastSuccess("Webhook endpoint created", config.url);
        },
      },
    );
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        {created ? (
          <div className="space-y-3">
            <DialogHeader>
              <DialogTitle>Endpoint created</DialogTitle>
              <DialogDescription>
                Deliveries to <span className="font-mono text-xs">{created.url}</span>{" "}
                start as soon as subscribed events fire.
              </DialogDescription>
            </DialogHeader>
            <SecretReveal
              secret={created.secret}
              context="This is the secret you just supplied. UBB stores only a signing copy and can never show it again — rotation is the only way to replace it."
            />
            <DialogFooter>
              <Button onClick={() => setOpen(false)}>Done</Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={(event) => void onSubmit(event)} className="space-y-4">
            <DialogHeader>
              <DialogTitle>Add webhook endpoint</DialogTitle>
              <DialogDescription>
                UBB will POST subscribed events to this URL, signed with your secret.
              </DialogDescription>
            </DialogHeader>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="webhook-create-url">Endpoint URL</Label>
              <Input
                id="webhook-create-url"
                placeholder="https://example.com/webhooks/ubb"
                autoComplete="off"
                spellCheck={false}
                {...form.register("url")}
              />
              {errors.url ? (
                <p className="text-xs text-destructive">{errors.url.message}</p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Must be HTTPS and publicly reachable — localhost and private
                  addresses are rejected.
                </p>
              )}
            </div>

            <SecretInput
              value={values.secret}
              onChange={(secret) =>
                form.setValue("secret", secret, { shouldValidate: isSubmitted })
              }
              error={errors.secret?.message}
            />

            <EventTypePicker
              allEvents={values.allEvents}
              onAllEventsChange={(allEvents) =>
                form.setValue("allEvents", allEvents, { shouldValidate: isSubmitted })
              }
              selected={values.eventTypes}
              onSelectedChange={(eventTypes) =>
                form.setValue("eventTypes", eventTypes, { shouldValidate: isSubmitted })
              }
              error={errors.eventTypes?.message}
            />

            <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2">
              <div>
                <Label htmlFor={activeId}>Start active</Label>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Paused endpoints keep their configuration but receive no deliveries.
                </p>
              </div>
              <Switch
                id={activeId}
                checked={values.isActive}
                onCheckedChange={(isActive) => form.setValue("isActive", isActive)}
              />
            </div>

            {create.isError && (
              <Alert>
                <TriangleAlert aria-hidden="true" />
                <AlertTitle>Couldn't create the endpoint</AlertTitle>
                <AlertDescription>{problemMessage(create.error)}</AlertDescription>
              </Alert>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "Working…" : "Create endpoint"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
