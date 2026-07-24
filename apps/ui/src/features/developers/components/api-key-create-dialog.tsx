// Create-key dialog: label + "Sandbox key" toggle. A sandbox key is minted
// on the sandbox sibling tenant and appears in ITS key list, not this one —
// the response's tenant_id says where it landed (surfaced by the caller in
// the return-once modal).

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

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
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

import { useCreateApiKey } from "../api/queries";
import type { ApiKeyCreated } from "../api/types";

const createKeySchema = z.object({
  label: z.string().trim().max(255, "Max 255 characters"),
  is_test: z.boolean(),
});

type CreateKeyValues = z.infer<typeof createKeySchema>;

export function ApiKeyCreateDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (created: ApiKeyCreated, wasTest: boolean) => void;
}) {
  const create = useCreateApiKey();
  const form = useForm<CreateKeyValues>({
    resolver: zodResolver(createKeySchema),
    defaultValues: { label: "", is_test: false },
  });
  const isTest = form.watch("is_test");

  const close = (next: boolean) => {
    if (create.isPending) return;
    onOpenChange(next);
    if (!next) {
      form.reset();
      create.reset();
    }
  };

  const submit = form.handleSubmit((values) => {
    create.mutate(values, {
      onSuccess: (created) => {
        onOpenChange(false);
        form.reset();
        create.reset();
        onCreated(created, values.is_test);
      },
    });
  });

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Create API key</DialogTitle>
          <DialogDescription>
            The full key is shown exactly once after creation.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void submit(event)} className="space-y-4">
          <FormField
            label="Label"
            error={form.formState.errors.label?.message}
            hint="A name for where this key is used, e.g. “Production backend”."
          >
            {(id) => (
              <Input
                id={id}
                autoFocus
                placeholder="Production backend"
                {...form.register("label")}
              />
            )}
          </FormField>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <Label htmlFor="create-key-sandbox">Sandbox key</Label>
              <p className="text-xs text-muted-foreground">
                Mints a <span className="font-mono">ubb_test_</span> key on
                your sandbox workspace instead of this one. It will appear in
                the sandbox's key list — not here — and the confirmation shows
                which workspace it landed on.
              </p>
            </div>
            <Switch
              id="create-key-sandbox"
              checked={isTest}
              onCheckedChange={(checked) =>
                form.setValue("is_test", checked === true)
              }
            />
          </div>
          {create.isError && (
            <p className="text-xs text-destructive">
              {problemMessage(create.error)}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => close(false)}
              disabled={create.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Working…" : "Create API key"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
