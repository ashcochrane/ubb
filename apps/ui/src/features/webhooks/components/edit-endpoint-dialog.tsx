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
import { toastSuccess } from "@/lib/mutations";

import { useUpdateWebhookConfig } from "../api/queries";
import type { WebhookConfig } from "../api/types";
import {
  editEndpointSchema,
  toEventTypesPayload,
  type EditEndpointValues,
} from "../lib/schemas";
import { EventTypePicker } from "./event-type-picker";

function defaultsFor(config: WebhookConfig): EditEndpointValues {
  return {
    url: config.url,
    allEvents: config.event_types.includes("*"),
    eventTypes: config.event_types.filter((eventType) => eventType !== "*"),
  };
}

/** PATCH url / event_types. The secret is untouchable here — rotation only. */
export function EditEndpointDialog({
  config,
  open,
  onOpenChange,
}: {
  config: WebhookConfig;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const update = useUpdateWebhookConfig();
  const form = useForm<EditEndpointValues>({
    resolver: zodResolver(editEndpointSchema),
    defaultValues: defaultsFor(config),
  });
  const { errors, isSubmitted } = form.formState;
  const values = form.watch();
  const { reset } = form;
  const resetMutation = update.reset;

  React.useEffect(() => {
    if (open) {
      reset(defaultsFor(config));
      resetMutation();
    }
  }, [open, config, reset, resetMutation]);

  const onSubmit = form.handleSubmit((formValues) => {
    update.mutate(
      {
        configId: config.id,
        body: {
          url: formValues.url,
          event_types: toEventTypesPayload(formValues),
        },
      },
      {
        onSuccess: (updated) => {
          toastSuccess("Endpoint updated", updated.url);
          onOpenChange(false);
        },
      },
    );
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={(event) => void onSubmit(event)} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Edit endpoint</DialogTitle>
            <DialogDescription>
              Change the URL or subscribed events in place. The signing secret can't be
              edited — use Rotate secret to replace it.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="webhook-edit-url">Endpoint URL</Label>
            <Input
              id="webhook-edit-url"
              autoComplete="off"
              spellCheck={false}
              {...form.register("url")}
            />
            {errors.url ? (
              <p className="text-xs text-destructive">{errors.url.message}</p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Must be HTTPS and publicly reachable — localhost and private addresses
                are rejected.
              </p>
            )}
          </div>

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

          {update.isError && (
            <Alert>
              <TriangleAlert aria-hidden="true" />
              <AlertTitle>Couldn't save the changes</AlertTitle>
              <AlertDescription>{problemMessage(update.error)}</AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Working…" : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
