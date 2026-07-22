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
import { useCreateBook } from "../api/queries";
import { bookCreateSchema, type BookCreateValues } from "../lib/schema";

/**
 * Create a rate card ("book") — a versioned set of provider rates. The card
 * starts at version 1; rates are added on the card's detail page and a new
 * version is minted when you publish changes.
 */
export function BookFormDialog({ trigger }: { trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  const create = useCreateBook();

  const form = useForm<BookCreateValues>({
    resolver: zodResolver(bookCreateSchema),
    defaultValues: {
      card_type: "",
      key: "",
      name: "",
      provider_key: "",
      currency: "",
      is_default: false,
    },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    await create.mutateAsync({
      card_type: values.card_type,
      key: values.key,
      name: values.name,
      provider_key: values.provider_key,
      currency: values.currency || null,
      is_default: values.is_default,
    });
    setOpen(false);
    form.reset();
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) form.reset();
      }}
    >
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>New rate card</DialogTitle>
            <DialogDescription>
              A rate card is a versioned set of provider rates. Give it a unique
              key and a type (e.g. cost or billing).
            </DialogDescription>
          </DialogHeader>

          <div className="mt-4 flex flex-col gap-4">
            <FormField
              label="Card type"
              error={errors.card_type?.message}
              hint="An open label grouping cards, e.g. cost or billing."
            >
              {(id) => (
                <Input id={id} placeholder="cost" {...form.register("card_type")} />
              )}
            </FormField>

            <FormField
              label="Key"
              error={errors.key?.message}
              hint="A unique, stable identifier for this card."
            >
              {(id) => (
                <Input id={id} placeholder="openai-standard" {...form.register("key")} />
              )}
            </FormField>

            <FormField label="Name" error={errors.name?.message}>
              {(id) => (
                <Input id={id} placeholder="OpenAI standard rates" {...form.register("name")} />
              )}
            </FormField>

            <FormField
              label="Provider key"
              error={errors.provider_key?.message}
              hint="Optional — scope the card to a single provider."
            >
              {(id) => (
                <Input id={id} placeholder="openai" {...form.register("provider_key")} />
              )}
            </FormField>

            <FormField
              label="Currency"
              error={errors.currency?.message}
              hint="Optional — defaults to the tenant currency (e.g. USD)."
            >
              {(id) => (
                <Input id={id} placeholder="USD" {...form.register("currency")} />
              )}
            </FormField>

            <Controller
              control={form.control}
              name="is_default"
              render={({ field }) => (
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={field.value}
                    onChange={(e) => field.onChange(e.target.checked)}
                    className="size-4 accent-foreground"
                  />
                  Make this the default card for its type
                </label>
              )}
            />
          </div>

          <DialogFooter className="mt-2">
            <DialogClose render={<Button variant="outline" type="button" disabled={create.isPending} />}>
              Cancel
            </DialogClose>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create rate card"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
