import { useMemo } from "react";
import { useFormContext, useFieldArray } from "react-hook-form";
import { Plus } from "lucide-react";
import type { WizardFormValues } from "../lib/schema";
import { DimensionCard } from "./dimension-card";
import { CostTester } from "./cost-tester";

const quickAdds = [
  { key: "grounding", label: "Grounding", type: "flat" as const, unit: "per request" },
  { key: "cached_tokens", label: "Cached tokens", type: "per_unit" as const, unit: "per 1M tokens" },
  { key: "image_tokens", label: "Image tokens", type: "per_unit" as const, unit: "per 1M tokens" },
  { key: "requests", label: "Requests", type: "flat" as const, unit: "per request" },
  { key: "search_queries", label: "Search queries", type: "flat" as const, unit: "per query" },
];

export function StepDimensions() {
  const { watch } = useFormContext<WizardFormValues>();
  const { fields, append, remove, insert } = useFieldArray<WizardFormValues>({
    name: "dimensions",
  });
  const dimensions = watch("dimensions");

  const duplicateKeys = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of dimensions) {
      if (d.key) counts[d.key] = (counts[d.key] ?? 0) + 1;
    }
    const dupes = new Set<string>();
    for (const [key, count] of Object.entries(counts)) {
      if (count > 1) dupes.add(key);
    }
    return dupes;
  }, [dimensions]);

  const existingKeys = new Set(dimensions.map((d) => d.key));

  const addDimension = () => {
    append({ key: "", type: "per_unit", price: 0, label: "", unit: "" });
  };

  const duplicateDimension = (index: number) => {
    const dim = dimensions[index];
    if (!dim) return;
    insert(index + 1, { ...dim, key: `${dim.key}_copy` });
  };

  const addQuick = (qa: typeof quickAdds[number]) => {
    if (existingKeys.has(qa.key)) return;
    append({ key: qa.key, type: qa.type, price: 0, label: qa.label, unit: qa.unit });
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[14px] font-medium">Define cost dimensions</h2>
        <p className="text-[12px] text-muted-foreground">
          Each dimension is one line item on your cost breakdown.
        </p>
      </div>

      <div className="space-y-3">
        {fields.map((field, idx) => (
          <DimensionCard
            key={field.id}
            index={idx}
            onRemove={() => remove(idx)}
            onDuplicate={() => duplicateDimension(idx)}
            duplicateKeys={duplicateKeys}
          />
        ))}
      </div>

      <button
        type="button"
        onClick={addDimension}
        className="flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed border-border py-3 text-[12px] text-muted-foreground hover:border-border-mid hover:bg-accent"
      >
        <Plus className="h-3.5 w-3.5" /> Add dimension
      </button>

      <div className="flex flex-wrap gap-1.5">
        {quickAdds
          .filter((qa) => !existingKeys.has(qa.key))
          .map((qa) => (
            <button
              key={qa.key}
              type="button"
              onClick={() => addQuick(qa)}
              className="rounded-full border border-border px-2.5 py-0.5 font-mono text-muted text-muted-foreground hover:border-muted-foreground hover:bg-accent"
            >
              + {qa.key}
            </button>
          ))}
      </div>

      <CostTester />
    </div>
  );
}
