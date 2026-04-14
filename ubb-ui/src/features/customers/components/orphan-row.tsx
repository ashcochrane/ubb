// src/features/customers/components/orphan-row.tsx
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { formatShortDate, formatMicros } from "@/lib/format";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAssignOrphan } from "../api/queries";
import type { CustomerMapping, OrphanedIdentifier } from "../api/types";

const assignSchema = z.object({
  stripeCustomerId: z.string().min(1, "Select a customer"),
});

type AssignFormValues = z.infer<typeof assignSchema>;

export function OrphanRow({
  orphan,
  customers,
}: {
  orphan: OrphanedIdentifier;
  customers: CustomerMapping[];
}) {
  const assignMutation = useAssignOrphan();
  const { control, handleSubmit } = useForm<AssignFormValues>({
    resolver: zodResolver(assignSchema),
    defaultValues: { stripeCustomerId: "" },
  });

  const onSubmit = (values: AssignFormValues) => {
    assignMutation.mutate({
      orphanId: orphan.id,
      stripeCustomerId: values.stripeCustomerId,
    });
  };

  const sortedCustomers = [...customers]
    .filter((c) => c.sdkIdentifier)
    .sort((a, b) => a.name.localeCompare(b.name));

  return (
    <tr className="border-b border-bg-subtle last:border-0 hover:bg-bg-subtle">
      <td className="px-3.5 py-2.5">
        <span className="font-mono text-[12px] font-medium text-red-text">
          {orphan.sdkIdentifier}
        </span>
      </td>
      <td className="px-3.5 py-2.5 text-[12px] text-text-secondary">
        {formatShortDate(orphan.firstSeenAt)}
      </td>
      <td className="px-3.5 py-2.5 text-right text-[12px] text-text-secondary">
        {orphan.eventCount}
      </td>
      <td className="px-3.5 py-2.5 text-right text-[12px] font-semibold text-red-text">
        {formatMicros(orphan.unattributedCost)}
      </td>
      <td className="px-3.5 py-2.5">
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex items-center gap-1.5"
        >
          <Controller
            name="stripeCustomerId"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger size="sm" className="min-w-[130px] text-[12px]">
                  <SelectValue placeholder="Select customer…" />
                </SelectTrigger>
                <SelectContent>
                  {sortedCustomers.map((c) => (
                    <SelectItem key={c.id} value={c.stripeCustomerId}>
                      {c.name} ({c.stripeCustomerId.slice(0, 7)})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <button
            type="submit"
            className="text-[11px] font-medium text-blue hover:underline"
            disabled={assignMutation.isPending}
          >
            {assignMutation.isPending ? "Assigning..." : "Assign"}
          </button>
        </form>
      </td>
    </tr>
  );
}
