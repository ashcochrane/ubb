import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
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
import { useTenantCurrency, type TenantConfig } from "@/hooks/use-tenant-config";
import { toastSuccess } from "@/lib/mutations";

import { useUpdateUndeclaredWorkCeilings } from "../api/queries";
import { altitudeLabel } from "../lib/kinds";
import {
  undeclaredWorkDefaults,
  undeclaredWorkPatch,
  undeclaredWorkSchema,
  type UndeclaredWorkValues,
} from "../lib/undeclared-work";

/**
 * Edit the workspace's default ceilings for work started with no declared
 * kind — one per altitude (#453, slice 6 §2, §18).
 *
 * These are the ceiling of the one "kind" a tenant can never declare, which
 * is why they are edited here on the Tasks page beside the declared kinds and
 * not on the settings page: a ceiling is a kernel setting, not a billing knob
 * (#141 §7). A declared kind of work never inherits them — it states its own
 * ceiling or declares itself uncapped — and the copy says so, because the
 * likeliest mistake here is raising a default and expecting a declared kind
 * to follow it.
 *
 * Empty is NO ceiling for that altitude, and the row renders it as exactly
 * that — never as "Uncapped", which is a declaration's word.
 */
export function UndeclaredWorkDialog({
  open,
  onOpenChange,
  config,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: TenantConfig;
}) {
  const currency = useTenantCurrency().toUpperCase();
  const update = useUpdateUndeclaredWorkCeilings();
  const form = useForm<UndeclaredWorkValues>({
    resolver: zodResolver(undeclaredWorkSchema),
    defaultValues: undeclaredWorkDefaults(config),
  });

  React.useEffect(() => {
    if (open) {
      form.reset(undeclaredWorkDefaults(config));
      update.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, config]);

  const onSubmit = (values: UndeclaredWorkValues) => {
    const patch = undeclaredWorkPatch(config, values);
    if (Object.keys(patch).length === 0) {
      onOpenChange(false);
      return;
    }
    update.mutate(patch, {
      onSuccess: () => {
        toastSuccess(
          "Default ceilings saved",
          "Work started with no declared kind runs under them from its next start.",
        );
        onOpenChange(false);
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Default ceilings for work with no declared kind</DialogTitle>
          <DialogDescription>
            The most a run may spend on supplier cost when it names no kind of work, at
            each altitude. A declared kind of work never inherits these — it states its own
            ceiling or declares itself uncapped. Leave a field empty for no ceiling.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void form.handleSubmit(onSubmit)(event)} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField
              label={`${altitudeLabel("task")} ceiling (${currency})`}
              error={form.formState.errors.wholeWork?.message}
              hint="For a whole unit of work started without a declared kind."
            >
              {(id) => (
                <Input
                  id={id}
                  inputMode="decimal"
                  placeholder="None"
                  {...form.register("wholeWork")}
                />
              )}
            </FormField>
            <FormField
              label={`${altitudeLabel("subtask")} ceiling (${currency})`}
              error={form.formState.errors.containedWork?.message}
              hint="For contained work started without a declared kind."
            >
              {(id) => (
                <Input
                  id={id}
                  inputMode="decimal"
                  placeholder="None"
                  {...form.register("containedWork")}
                />
              )}
            </FormField>
          </div>

          {update.isError && (
            <p className="text-xs text-destructive">{problemMessage(update.error)}</p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={update.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Working…" : "Save default ceilings"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
