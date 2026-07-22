import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { ChevronDown, ChevronUp, Copy, Trash2 } from "lucide-react";
import type { WizardFormValues } from "../lib/schema";
import { cn } from "@/lib/utils";

interface DimensionCardProps {
  index: number;
  onRemove: () => void;
  onDuplicate: () => void;
  duplicateKeys: Set<string>;
}

export function DimensionCard({ index, onRemove, onDuplicate, duplicateKeys }: DimensionCardProps) {
  const [collapsed, setCollapsed] = useState(false);
  const { register, watch, setValue } = useFormContext<WizardFormValues>();

  const metricName = watch(`dimensions.${index}.metricName`);
  const pricingType = watch(`dimensions.${index}.pricingType`);
  const costPerUnitMicros = watch(`dimensions.${index}.costPerUnitMicros`);
  const isDuplicate = metricName ? duplicateKeys.has(metricName) : false;

  return (
    <div className="rounded-md border border-border bg-bg-surface px-4 py-3 transition-colors hover:border-border-mid">
      <div className="flex items-center justify-between">
        <div className="text-[12px] font-medium">
          Dimension {index + 1}
          {collapsed && metricName && (
            <span className="ml-2 font-mono text-muted-foreground">{metricName}</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setCollapsed(!collapsed)} className="rounded p-1 text-muted-foreground hover:bg-accent">
            {collapsed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
          </button>
          <button type="button" onClick={onDuplicate} className="rounded p-1 text-muted-foreground hover:bg-accent">
            <Copy className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={onRemove} className="rounded p-1 text-muted-foreground hover:bg-red-light hover:text-red">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-[1fr_auto] gap-3">
            <div>
              <label className="mb-1 block text-muted font-medium">Metric name</label>
              <input
                {...register(`dimensions.${index}.metricName`)}
                placeholder="e.g. input_tokens"
                className={cn(
                  "w-full rounded-lg border bg-background px-3 py-1.5 font-mono text-[12px] outline-none focus:border-muted-foreground",
                  isDuplicate ? "border-red" : "border-border",
                )}
              />
              {isDuplicate && (
                <p className="mt-0.5 text-muted text-red">(duplicate metric name!)</p>
              )}
              <p className="mt-0.5 text-muted text-muted-foreground">
                Must match the key your SDK sends.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-muted font-medium">Pricing type</label>
              <div className="flex rounded-lg border border-border">
                <button
                  type="button"
                  onClick={() => setValue(`dimensions.${index}.pricingType`, "per_unit")}
                  className={cn(
                    "px-3 py-1.5 text-label transition-colors",
                    pricingType === "per_unit" ? "bg-foreground text-background" : "text-muted-foreground hover:bg-accent",
                  )}
                >
                  Per unit
                </button>
                <button
                  type="button"
                  onClick={() => setValue(`dimensions.${index}.pricingType`, "flat")}
                  className={cn(
                    "px-3 py-1.5 text-label transition-colors",
                    pricingType === "flat" ? "bg-foreground text-background" : "text-muted-foreground hover:bg-accent",
                  )}
                >
                  Flat
                </button>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-muted font-medium">Your cost (micros)</label>
              <input
                type="number"
                step="1"
                min="0"
                {...register(`dimensions.${index}.costPerUnitMicros`, { valueAsNumber: true })}
                placeholder="e.g. 100"
                className="w-full rounded-lg border border-border bg-background py-1.5 px-3 font-mono text-[12px] outline-none focus:border-muted-foreground"
              />
              <p className="mt-0.5 text-muted text-muted-foreground">
                {pricingType === "per_unit" ? "Price per single unit." : "Fixed cost each time this fires."}
                {costPerUnitMicros > 0 && (
                  <> ({(costPerUnitMicros / 1_000_000).toFixed(8).replace(/0+$/, "").replace(/\.$/, "")} USD)</>
                )}
              </p>
              {pricingType === "per_unit" && costPerUnitMicros > 1_000 && (
                <div className="mt-1 rounded-md bg-amber-light px-2 py-1 text-muted text-amber-text">
                  This seems high for a per-unit price. Double-check.
                </div>
              )}
            </div>

            <div>
              <label className="mb-1 block text-muted font-medium">Provider cost (micros)</label>
              <input
                type="number"
                step="1"
                min="0"
                {...register(`dimensions.${index}.providerCostPerUnitMicros`, {
                  setValueAs: (v) => (v === "" || v === null || v === undefined ? null : Number(v)),
                })}
                placeholder="optional"
                className="w-full rounded-lg border border-border bg-background py-1.5 px-3 font-mono text-[12px] outline-none focus:border-muted-foreground"
              />
              <p className="mt-0.5 text-muted text-muted-foreground">
                What the provider charges you. Used for margin display.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-muted font-medium">Unit quantity</label>
              <input
                type="number"
                step="1"
                min="1"
                {...register(`dimensions.${index}.unitQuantity`, { valueAsNumber: true })}
                placeholder="1"
                className="w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-[12px] outline-none focus:border-muted-foreground"
              />
              <p className="mt-0.5 text-muted text-muted-foreground">e.g. 1000000 for "per 1M"</p>
            </div>
            <div>
              <label className="mb-1 block text-muted font-medium">Display label</label>
              <input
                {...register(`dimensions.${index}.label`)}
                placeholder="e.g. Input tokens"
                className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
              />
            </div>
            <div>
              <label className="mb-1 block text-muted font-medium">Display unit</label>
              <input
                {...register(`dimensions.${index}.unit`)}
                placeholder="e.g. per 1M tokens"
                className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-muted font-medium">Currency</label>
            <input
              {...register(`dimensions.${index}.currency`)}
              placeholder="USD"
              maxLength={3}
              className="w-32 rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-[12px] outline-none focus:border-muted-foreground"
            />
          </div>
        </div>
      )}
    </div>
  );
}
