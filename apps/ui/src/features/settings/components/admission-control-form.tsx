import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toastSuccess } from "@/lib/mutations";

import { useUpdateTenantConfig } from "../api/queries";
import type { TenantConfig } from "../api/types";
import {
  admissionControlSchema,
  buildAdmissionPatch,
  configToAdmissionValues,
  type AdmissionControlValues,
} from "../lib/settings";

/** The one label the field carries; the card's test spells it itself. */
const NEW_WORK_PER_MINUTE_LABEL = "New work per minute, per customer";

/**
 * Admission control's one setting (#462, slice 6 §6, §18): how many new
 * top-level pieces of work one customer may start in a minute. It is NOT
 * spend control — it bounds how fast work enters and says nothing about
 * cost — and it applies to every workspace, whichever way it bills, which is
 * why it stands on its own rather than inside the wallet floors' form, which
 * hides itself under postpaid.
 */
export function AdmissionControlForm({
  config,
  isAdmin,
}: {
  config: TenantConfig;
  isAdmin: boolean;
}) {
  const mutation = useUpdateTenantConfig();
  const form = useForm<AdmissionControlValues>({
    resolver: zodResolver(admissionControlSchema),
    defaultValues: configToAdmissionValues(config),
  });
  const errors = form.formState.errors;

  const onSubmit = (values: AdmissionControlValues) => {
    const patch = buildAdmissionPatch(config, values);
    if (Object.keys(patch).length === 0) return;
    mutation.mutate(patch, {
      onSuccess: (updated) => {
        form.reset(configToAdmissionValues(updated));
        toastSuccess("New-work rate saved");
      },
    });
  };

  return (
    <form
      onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
      className="space-y-4"
      noValidate
    >
      <FormField
        label={NEW_WORK_PER_MINUTE_LABEL}
        error={errors.newWorkPerMinute?.message}
        hint="How many new top-level pieces of work one customer may start in a minute. Over it, a start answers 429 with Retry-After until the minute turns; retries, contained work, usage reports and closes never count against it. This bounds how fast work enters, not what it spends. Leave empty for no bound."
      >
        {(id) => (
          <Input
            id={id}
            type="number"
            step="1"
            min="1"
            disabled={!isAdmin}
            placeholder="None"
            {...form.register("newWorkPerMinute")}
          />
        )}
      </FormField>

      {mutation.isError && (
        <p className="text-xs text-destructive">
          {problemMessage(mutation.error)}
        </p>
      )}

      <div className="flex justify-end">
        <Button
          type="submit"
          size="sm"
          disabled={!isAdmin || mutation.isPending || !form.formState.isDirty}
        >
          {mutation.isPending ? "Working…" : "Save new-work rate"}
        </Button>
      </div>
    </form>
  );
}
