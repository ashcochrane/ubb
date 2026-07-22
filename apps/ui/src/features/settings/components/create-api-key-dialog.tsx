import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
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
import { CheckboxRow } from "./checkbox-row";
import { useCreateApiKey } from "../api/queries";
import { readRawKey } from "../api/types";
import { apiKeyCreateSchema, type ApiKeyCreateValues } from "../lib/schema";

/**
 * Mint an API key. The raw key is returned exactly once by the backend, under
 * an untyped `object` response — we probe the known field names and reveal it
 * with a copy affordance and a "won't be shown again" warning.
 */
export function CreateApiKeyDialog() {
  const [open, setOpen] = useState(false);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const create = useCreateApiKey();

  const form = useForm<ApiKeyCreateValues>({
    resolver: zodResolver(apiKeyCreateSchema),
    defaultValues: { label: "", is_test: false },
  });

  const reset = () => {
    form.reset({ label: "", is_test: false });
    setCreatedKey(null);
    setRevealed(false);
  };

  const onSubmit = form.handleSubmit(async (values) => {
    const result = await create.mutateAsync(values);
    setCreatedKey(readRawKey(result));
    setRevealed(true);
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) reset();
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm">
            <Plus />
            Create key
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        {revealed ? (
          <>
            <DialogHeader>
              <DialogTitle>API key created</DialogTitle>
              <DialogDescription>
                Copy this key now — it is shown only once and can never be
                retrieved again.
              </DialogDescription>
            </DialogHeader>
            {createdKey ? (
              <CopyField label="Secret key" value={createdKey} />
            ) : (
              <p className="text-sm text-muted-foreground">
                The key was created but the raw value was not returned by the
                API. Rotate the key to obtain a fresh secret.
              </p>
            )}
            <DialogFooter>
              <DialogClose render={<Button />}>Done</DialogClose>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={onSubmit}>
            <DialogHeader>
              <DialogTitle>New API key</DialogTitle>
              <DialogDescription>
                Give the key a label so you can recognise it later.
              </DialogDescription>
            </DialogHeader>
            <div className="mt-4 flex flex-col gap-4">
              <FormField label="Label" error={form.formState.errors.label?.message}>
                {(id) => (
                  <Input id={id} placeholder="e.g. Production server" {...form.register("label")} />
                )}
              </FormField>
              <Controller
                control={form.control}
                name="is_test"
                render={({ field }) => (
                  <CheckboxRow
                    checked={field.value}
                    onChange={field.onChange}
                    label="Test key"
                    description="Mint a sandbox (ubb_test_) key instead of a live one."
                  />
                )}
              />
            </div>
            <DialogFooter className="mt-2">
              <DialogClose render={<Button variant="outline" type="button" disabled={create.isPending} />}>
                Cancel
              </DialogClose>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "Creating…" : "Create key"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
