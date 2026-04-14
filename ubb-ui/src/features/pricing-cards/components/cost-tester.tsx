import { useState, useMemo } from "react";
import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";
import { calculateCosts, projectCosts } from "../lib/calculations";

export function CostTester() {
  const { watch } = useFormContext<WizardFormValues>();
  const dimensions = watch("dimensions");
  const [quantities, setQuantities] = useState<Record<string, number>>({});

  const result = useMemo(
    () => calculateCosts(dimensions, quantities),
    [dimensions, quantities],
  );

  const projection = useMemo(
    () => projectCosts(result.total, 1000),
    [result.total],
  );

  const setQty = (key: string, value: number) => {
    setQuantities((prev) => ({ ...prev, [key]: value }));
  };

  if (dimensions.length === 0) return null;

  return (
    <div className="rounded-md border border-border bg-bg-subtle px-4 py-3.5">
      <div className="mb-0.5 flex items-center gap-2">
        <span className="text-[13px] font-medium">Live cost tester</span>
        <span className="rounded-full bg-blue-light px-2 py-0.5 text-muted text-blue-text">
          Updates as you type
        </span>
      </div>
      <p className="mb-3 text-label text-muted-foreground">
        Enter sample quantities to see calculated costs in real time.
      </p>

      <div className="space-y-1.5">
        {result.dimensions.map((d) => (
          <div key={d.key} className="grid grid-cols-[1fr_100px_120px] items-center gap-2">
            <span className="font-mono text-label text-muted-foreground">{d.key}</span>
            <input
              type="number"
              value={quantities[d.key] ?? ""}
              onChange={(e) => setQty(d.key, Number(e.target.value) || 0)}
              placeholder={d.type === "flat" ? "1" : "1000"}
              className="rounded-md border border-border bg-background px-2 py-1 text-right font-mono text-label outline-none focus:border-muted-foreground"
            />
            <span className="text-right font-mono text-label text-muted-foreground">
              {d.quantity > 0
                ? `${d.quantity.toLocaleString()} × $${d.price} = $${d.cost.toFixed(6)}`
                : "—"}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 border-t border-border pt-2">
        <div className="flex items-center justify-between">
          <span className="text-[12px] font-medium">Total event cost</span>
          <span className="font-mono text-[13px] font-medium">
            ${result.total.toFixed(6)}
          </span>
        </div>
        {result.total > 0 && (
          <p className="mt-1 text-muted text-muted-foreground">
            Approx ${projection.daily.toFixed(2)} per 1,000 events at this volume
          </p>
        )}
      </div>
    </div>
  );
}
