import { useState, useMemo } from "react";
import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";
import { calculateCosts, calculateDistribution, projectCosts } from "../lib/calculations";

const BAR_COLORS = ["#378ADD", "#7F77DD", "#D85A30", "#3B6D11", "#854F0B"];

/** Wrapper that remounts the simulator when dimension keys change. */
export function DryRunSimulator() {
  const { watch } = useFormContext<WizardFormValues>();
  const dimensions = watch("dimensions");
  const keysStr = dimensions.map((d) => d.key).join(",");
  return <DryRunSimulatorInner key={keysStr} />;
}

function DryRunSimulatorInner() {
  const { watch } = useFormContext<WizardFormValues>();
  const dimensions = watch("dimensions");
  const [quantities, setQuantities] = useState<Record<string, number>>(() => {
    const init: Record<string, number> = {};
    for (const d of dimensions) {
      init[d.key] = d.type === "flat" ? 1 : 1000;
    }
    return init;
  });

  const result = useMemo(() => calculateCosts(dimensions, quantities), [dimensions, quantities]);
  const distribution = useMemo(() => calculateDistribution(result), [result]);
  const projection = useMemo(() => projectCosts(result.total, 1000), [result.total]);

  const dominant = distribution.length > 0 && distribution[0].percentage > 90 ? distribution[0] : null;

  const setQty = (key: string, value: number) => {
    setQuantities((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="rounded-xl border border-border bg-accent/30 px-4 py-4">
      <div className="mb-0.5 flex items-center justify-between">
        <span className="text-[13px] font-medium">Dry-run simulator</span>
        {result.total > 0 && (
          <span className="rounded-full bg-green-50 px-2 py-0.5 text-[10px] text-green-700 dark:bg-green-900/20 dark:text-green-400">
            Looks correct
          </span>
        )}
      </div>
      <p className="mb-3 text-[11px] text-muted-foreground">
        Enter realistic sample quantities for a single API call.
      </p>

      <div className="space-y-1.5">
        {result.dimensions.map((d) => (
          <div key={d.key} className="grid grid-cols-[130px_100px_1fr] items-center gap-2">
            <span className="font-mono text-[11px] text-muted-foreground">{d.key}</span>
            <input
              type="number"
              value={quantities[d.key] ?? ""}
              onChange={(e) => setQty(d.key, Number(e.target.value) || 0)}
              className="rounded-md border border-border bg-background px-2 py-1 text-right font-mono text-[11px] outline-none focus:border-muted-foreground"
            />
            <span className="text-right font-mono text-[11px] text-muted-foreground">
              {d.quantity > 0
                ? `${d.quantity.toLocaleString()} × $${d.price} = $${d.cost.toFixed(6)}`
                : "—"}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 border-t border-border pt-2 space-y-1">
        {result.dimensions.map((d) => (
          <div key={d.key} className="flex justify-between text-[11px]">
            <span className="text-muted-foreground">{d.label}</span>
            <span className="font-mono font-medium">${d.cost.toFixed(6)}</span>
          </div>
        ))}
      </div>

      <div className="mt-2 border-t border-border pt-2 flex justify-between">
        <span className="text-[13px] font-medium">Total per event</span>
        <span className="font-mono text-[14px] font-medium">${result.total.toFixed(6)}</span>
      </div>

      {result.total > 0 && (
        <p className="mt-1 text-[10px] text-muted-foreground">
          At 1,000 events/day: ~${projection.daily.toFixed(2)}/day · ~${projection.monthly.toFixed(0)}/month
        </p>
      )}

      {distribution.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[10px] text-muted-foreground">Cost distribution</div>
          <div className="flex h-2 overflow-hidden rounded-full">
            {distribution.map((d, i) => (
              <div
                key={d.key}
                className="h-full"
                style={{
                  width: `${Math.max(d.percentage, 0.3)}%`,
                  backgroundColor: BAR_COLORS[i % BAR_COLORS.length],
                }}
              />
            ))}
          </div>
          <div className="mt-1 flex flex-wrap gap-3">
            {distribution.map((d, i) => (
              <div key={d.key} className="flex items-center gap-1 text-[10px] text-muted-foreground">
                <div className="h-2 w-2 rounded-full" style={{ backgroundColor: BAR_COLORS[i % BAR_COLORS.length] }} />
                {d.label} {d.percentage.toFixed(1)}%
              </div>
            ))}
          </div>
        </div>
      )}

      {dominant && (
        <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 dark:border-amber-700 dark:bg-amber-900/20">
          <div className="text-[11px] font-medium text-amber-700 dark:text-amber-400">
            Dominated by one dimension
          </div>
          <p className="text-[10px] text-amber-600 dark:text-amber-400">
            {dominant.label} accounts for {dominant.percentage.toFixed(1)}% of total cost. Is this expected?
          </p>
        </div>
      )}
    </div>
  );
}
