// src/features/customers/components/customer-row-edit.tsx
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useUpdateMapping } from "../api/queries";

const mappingSchema = z.object({
  sdkIdentifier: z.string().min(1, "SDK identifier is required"),
});

type MappingFormValues = z.infer<typeof mappingSchema>;

interface InlineEditCellProps {
  customerId: string;
  defaultValue: string;
  isNew: boolean;
  onDone: () => void;
}

export function InlineEditCell({
  customerId,
  defaultValue,
  isNew,
  onDone,
}: InlineEditCellProps) {
  const { register, handleSubmit } = useForm<MappingFormValues>({
    resolver: zodResolver(mappingSchema),
    defaultValues: { sdkIdentifier: defaultValue },
  });
  const mutation = useUpdateMapping();

  const onSubmit = (values: MappingFormValues) => {
    mutation.mutate(
      { customerId, sdkIdentifier: values.sdkIdentifier },
      { onSuccess: onDone },
    );
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex items-center gap-1.5">
      <input
        {...register("sdkIdentifier")}
        className="rounded-sm border border-blue-border bg-bg-surface px-2 py-1 font-mono text-[12px] text-text-primary outline-none focus:border-blue focus:ring-2 focus:ring-blue/15"
        placeholder="Enter identifier…"
        autoFocus={!isNew}
      />
      <button
        type="submit"
        className="text-[11px] font-medium text-blue hover:underline"
        disabled={mutation.isPending}
      >
        {isNew ? "Map" : "Save"}
      </button>
      {!isNew && (
        <button
          type="button"
          className="text-[11px] text-text-muted hover:underline"
          onClick={onDone}
        >
          Cancel
        </button>
      )}
    </form>
  );
}
