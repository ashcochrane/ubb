import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import type { PricingCard } from "../api/types";
import { useGroups, useUpdateCard } from "../api/queries";
import { cardEditSchema, type CardEditFormValues } from "../lib/schema";

export function CardEditForm({ card }: { card: PricingCard }) {
  const groups = useGroups();
  const update = useUpdateCard(card.id);

  const { register, handleSubmit, reset, formState: { errors } } =
    useForm<CardEditFormValues>({
      resolver: zodResolver(cardEditSchema),
      defaultValues: {
        name: card.name,
        description: card.description ?? "",
        pricingSourceUrl: card.pricingSourceUrl ?? "",
        groupId: card.groupId ?? null,
      },
    });

  // Re-sync form when card changes (e.g. after a save). Depend on primitives,
  // not the card object reference, to avoid infinite-render loops in tests.
  const cardId = card.id;
  useEffect(() => {
    reset({
      name: card.name,
      description: card.description ?? "",
      pricingSourceUrl: card.pricingSourceUrl ?? "",
      groupId: card.groupId ?? null,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cardId, reset]);

  async function onSubmit(values: CardEditFormValues) {
    await update.mutateAsync({
      name: values.name,
      description: values.description,
      pricingSourceUrl: values.pricingSourceUrl,
      groupId: values.groupId,
    });
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <FormField label="Name" error={errors.name?.message}>
        {(id) => <Input id={id} {...register("name")} />}
      </FormField>
      <FormField label="Description" error={errors.description?.message}>
        {(id) => <Input id={id} {...register("description")} />}
      </FormField>
      <FormField label="Pricing source URL" error={errors.pricingSourceUrl?.message}>
        {(id) => <Input id={id} {...register("pricingSourceUrl")} />}
      </FormField>
      <FormField label="Group" error={errors.groupId?.message}>
        {(id) => (
          <select
            id={id}
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            {...register("groupId", {
              setValueAs: (v) => (v === "" ? null : v),
            })}
          >
            <option value="">No group</option>
            {(groups.data ?? []).map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        )}
      </FormField>
      <Button type="submit" disabled={update.isPending}>
        {update.isPending ? "Saving…" : "Save card"}
      </Button>
    </form>
  );
}
