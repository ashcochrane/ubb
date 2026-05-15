import { useState } from "react";
import { Check, X, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatCostMicros } from "@/lib/format";
import type { EventFilterOptions, StagedEvent, ValidationError } from "../api/types";

interface StagingSectionProps {
  events: StagedEvent[];
  filterOptions: EventFilterOptions;
  reason: string;
  onReasonChange: (r: string) => void;
  onEventsChange: (events: StagedEvent[]) => void;
  onAddRow: () => void;
  onClearAll: () => void;
  onPush: () => void;
  isPushing: boolean;
  pushResult: string | null;
}

/** Extract the single metric name from usageMetrics (one-metric-per-row strategy). */
function getMetric(ev: StagedEvent): string {
  return Object.keys(ev.usageMetrics)[0] ?? "";
}

/** Extract the single quantity from usageMetrics. */
function getQty(ev: StagedEvent): number {
  return Object.values(ev.usageMetrics)[0] ?? 0;
}

function validate(r: StagedEvent, opts: EventFilterOptions): ValidationError[] {
  const e: ValidationError[] = [];
  if (!r.effectiveAt) e.push({ field: "effectiveAt", message: "Date required" });
  if (!r.customerExternalId) e.push({ field: "customerExternalId", message: "Customer required" });
  else if (!opts.customers.some((c) => c.key === r.customerExternalId))
    e.push({ field: "customerExternalId", message: `Unknown: ${r.customerExternalId}`, warning: true });
  if (!r.pricingCard) e.push({ field: "pricingCard", message: "Card required" });
  else if (!opts.cards.some((c) => c.key === r.pricingCard))
    e.push({ field: "pricingCard", message: `Unknown card: ${r.pricingCard}` });
  const metric = getMetric(r);
  if (!metric) e.push({ field: "usageMetrics", message: "Metric required" });
  else if (r.pricingCard && opts.cardDimensions[r.pricingCard] && !opts.cardDimensions[r.pricingCard]!.includes(metric))
    e.push({ field: "usageMetrics", message: `${metric} not on ${r.pricingCard}` });
  const qty = getQty(r);
  if (!qty || qty <= 0) e.push({ field: "quantity", message: "Qty must be > 0" });
  return e;
}

function ValidationIcon({ errors }: { errors: ValidationError[] }) {
  const hardErrors = errors.filter((e) => !e.warning);
  const warnings = errors.filter((e) => e.warning);

  if (hardErrors.length > 0) {
    return (
      <div className="group relative flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-light">
        <X className="h-2.5 w-2.5 text-red-text" />
        <div className="absolute left-5 top-[-2px] z-10 hidden whitespace-nowrap rounded-md border border-red-border bg-bg-surface px-2 py-1 text-[9px] text-red-text shadow-sm group-hover:block">
          {hardErrors.map((e) => e.message).join(". ")}
        </div>
      </div>
    );
  }
  if (warnings.length > 0) {
    return (
      <div className="group relative flex h-3.5 w-3.5 items-center justify-center rounded-full bg-amber-light">
        <AlertTriangle className="h-2.5 w-2.5 text-amber-text" />
        <div className="absolute left-5 top-[-2px] z-10 hidden whitespace-nowrap rounded-md border border-amber-border bg-bg-surface px-2 py-1 text-[9px] text-amber-text shadow-sm group-hover:block">
          {warnings.map((e) => e.message).join(". ")}
        </div>
      </div>
    );
  }
  return (
    <div className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-green-light">
      <Check className="h-2.5 w-2.5 text-green-text" />
    </div>
  );
}

export function StagingSection({
  events,
  filterOptions,
  reason,
  onReasonChange,
  onEventsChange,
  onAddRow,
  onClearAll,
  onPush,
  isPushing,
  pushResult,
}: StagingSectionProps) {
  const [editingCell, setEditingCell] = useState<{ row: number; field: string } | null>(null);

  const allValidations = events.map((ev) => validate(ev, filterOptions));
  const errorCount = allValidations.filter((v) => v.some((e) => !e.warning)).length;
  const canPush = events.length > 0 && errorCount === 0 && reason.trim().length > 0;

  // Estimated total cost from staging grid (in micros)
  let totalCostMicros = 0;
  for (const ev of events) {
    for (const [metricName, qty] of Object.entries(ev.usageMetrics)) {
      const priceInfo = filterOptions.dimensionPrices[metricName];
      const unitCost = priceInfo ? priceInfo.costPerUnitMicros / priceInfo.unitQuantity : 0;
      totalCostMicros += qty * unitCost;
    }
  }

  function updateEvent(idx: number, partial: Partial<StagedEvent>) {
    const updated = [...events];
    updated[idx] = { ...updated[idx]!, ...partial };
    onEventsChange(updated);
  }

  /** Update the metric name (key) in usageMetrics, preserving the quantity. */
  function updateMetric(idx: number, newMetric: string) {
    const ev = events[idx]!;
    const qty = getQty(ev);
    const newMetrics: Record<string, number> = newMetric ? { [newMetric]: qty } : {};
    updateEvent(idx, { usageMetrics: newMetrics });
  }

  /** Update the quantity in usageMetrics, preserving the metric name. */
  function updateQty(idx: number, qty: number) {
    const ev = events[idx]!;
    const metric = getMetric(ev);
    const newMetrics: Record<string, number> = metric ? { [metric]: qty } : {};
    updateEvent(idx, { usageMetrics: newMetrics });
  }

  /** When card changes, auto-select the first dimension if only one exists. */
  function updateCard(idx: number, pricingCard: string) {
    const dims = filterOptions.cardDimensions[pricingCard] ?? [];
    const currentMetric = getMetric(events[idx]!);
    const qty = getQty(events[idx]!);
    const newMetric = dims.length === 1 ? dims[0]! : (dims.includes(currentMetric) ? currentMetric : "");
    const newMetrics: Record<string, number> = newMetric ? { [newMetric]: qty } : {};
    updateEvent(idx, { pricingCard, usageMetrics: newMetrics });
  }

  function removeEvent(idx: number) {
    onEventsChange(events.filter((_, i) => i !== idx));
  }

  function cellOutline(errors: ValidationError[], field: string) {
    if (errors.some((e) => e.field === field && !e.warning)) return "outline outline-[1.5px] -outline-offset-1 outline-red rounded-sm";
    if (errors.some((e) => e.field === field && e.warning)) return "outline outline-[1.5px] -outline-offset-1 outline-amber rounded-sm";
    return "";
  }

  const editCell = "cursor-pointer rounded-sm transition-colors hover:bg-accent-ghost relative";
  const inputClass = "w-full rounded-sm border border-accent-border bg-bg-surface px-1.5 py-0.5 text-[10px] text-text-primary outline-none focus:ring-2 focus:ring-accent-base/15";

  return (
    <div className="overflow-hidden rounded-md border border-accent-border bg-bg-surface">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-accent-border bg-accent-ghost px-4 py-2.5">
        <div className="flex items-center gap-2 text-[12px] font-semibold text-accent-text">
          <span>{events.length}</span> staged rows
          {events.length > 0 && (
            <span className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-medium",
              errorCount > 0 ? "bg-red-light text-red-text" : "bg-green-light text-green-text",
            )}>
              {errorCount > 0 ? `${errorCount} error${errorCount > 1 ? "s" : ""}` : "All valid"}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            className="rounded-full border border-accent-border bg-bg-surface px-2.5 py-0.5 text-[10px] font-medium text-accent-text hover:bg-accent-ghost"
            onClick={onAddRow}
          >
            + Row
          </button>
          <button className="text-[10px] text-text-muted hover:text-text-secondary" onClick={onClearAll}>
            Clear all
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="max-h-[220px] overflow-auto">
        <table className="w-full min-w-[720px] border-collapse text-[10px]">
          <thead>
            <tr>
              {["", "TIME", "CUSTOMER", "GROUP", "CARD", "METRIC", "QTY", "EST. COST", ""].map((h, i) => (
                <th key={i} className={cn(
                  "sticky top-0 z-[2] border-b border-border bg-bg-subtle p-1.5 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted",
                  i === 0 && "w-[22px]",
                  i === 1 && "w-[88px] text-left",
                  i === 2 && "w-[82px] text-left",
                  i === 3 && "w-[82px] text-left",
                  i === 4 && "w-[82px] text-left",
                  i === 5 && "w-[90px] text-left",
                  i === 6 && "w-[50px] text-right",
                  i === 7 && "w-[80px] text-right",
                  i === 8 && "w-[24px]",
                )}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.map((ev, i) => {
              const errors = allValidations[i]!;
              const metric = getMetric(ev);
              const qty = getQty(ev);
              const priceInfo = filterOptions.dimensionPrices[metric];
              const unitCost = priceInfo ? priceInfo.costPerUnitMicros / priceInfo.unitQuantity : 0;
              const estCostMicros = qty * unitCost;
              const costStr = estCostMicros > 0 ? formatCostMicros(Math.round(estCostMicros)) : "\u2014";
              const isEditing = editingCell?.row === i;

              return (
                <tr key={i} className="border-b border-bg-subtle last:border-0 hover:bg-bg-page">
                  <td className="p-1 text-center"><ValidationIcon errors={errors} /></td>
                  {/* effectiveAt */}
                  <td className={cn("p-1", editCell, cellOutline(errors, "effectiveAt"))}>
                    {isEditing && editingCell.field === "effectiveAt" ? (
                      <input type="date" defaultValue={ev.effectiveAt} autoFocus className={cn(inputClass, "font-mono")}
                        onBlur={(e) => { updateEvent(i, { effectiveAt: e.target.value }); setEditingCell(null); }}
                        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
                    ) : (
                      <span className="font-mono text-accent-text" onClick={() => setEditingCell({ row: i, field: "effectiveAt" })}>
                        {ev.effectiveAt || <span className="font-sans italic text-amber-text">set date</span>}
                      </span>
                    )}
                  </td>
                  {/* customerExternalId */}
                  <td className={cn("p-1", editCell, cellOutline(errors, "customerExternalId"))}>
                    {isEditing && editingCell.field === "customerExternalId" ? (
                      <select defaultValue={ev.customerExternalId} autoFocus className={inputClass}
                        onBlur={(e) => { updateEvent(i, { customerExternalId: e.target.value }); setEditingCell(null); }}
                        onChange={(e) => { updateEvent(i, { customerExternalId: e.target.value }); setEditingCell(null); }}>
                        <option value="">Select...</option>
                        {filterOptions.customers.map((c) => <option key={c.key} value={c.key}>{c.key}</option>)}
                      </select>
                    ) : (
                      <span className="font-medium text-accent-text" onClick={() => setEditingCell({ row: i, field: "customerExternalId" })}>
                        {ev.customerExternalId || <span className="font-normal italic text-amber-text">set customer</span>}
                      </span>
                    )}
                  </td>
                  {/* group */}
                  <td className={cn("p-1", editCell)}>
                    {isEditing && editingCell.field === "group" ? (
                      <select defaultValue={ev.group} autoFocus className={inputClass}
                        onBlur={(e) => { updateEvent(i, { group: e.target.value }); setEditingCell(null); }}
                        onChange={(e) => { updateEvent(i, { group: e.target.value }); setEditingCell(null); }}>
                        <option value="">(none)</option>
                        {filterOptions.groups.map((g) => <option key={g.key} value={g.key}>{g.key}</option>)}
                      </select>
                    ) : (
                      <span className="font-mono text-accent-text" onClick={() => setEditingCell({ row: i, field: "group" })}>
                        {ev.group || <span className="text-text-muted">&mdash;</span>}
                      </span>
                    )}
                  </td>
                  {/* pricingCard */}
                  <td className={cn("p-1", editCell, cellOutline(errors, "pricingCard"))}>
                    {isEditing && editingCell.field === "pricingCard" ? (
                      <select defaultValue={ev.pricingCard} autoFocus className={inputClass}
                        onBlur={(e) => { updateCard(i, e.target.value); setEditingCell(null); }}
                        onChange={(e) => { updateCard(i, e.target.value); setEditingCell(null); }}>
                        <option value="">Select...</option>
                        {filterOptions.cards.map((c) => <option key={c.key} value={c.key}>{c.key}</option>)}
                      </select>
                    ) : (
                      <span className="text-accent-text" onClick={() => setEditingCell({ row: i, field: "pricingCard" })}>
                        {ev.pricingCard || <span className="italic text-amber-text">set card</span>}
                      </span>
                    )}
                  </td>
                  {/* metric (from usageMetrics key) */}
                  <td className={cn("p-1", editCell, cellOutline(errors, "usageMetrics"))}>
                    {isEditing && editingCell.field === "metric" ? (
                      <select defaultValue={metric} autoFocus className={inputClass}
                        onBlur={(e) => { updateMetric(i, e.target.value); setEditingCell(null); }}
                        onChange={(e) => { updateMetric(i, e.target.value); setEditingCell(null); }}>
                        <option value="">Select...</option>
                        {(filterOptions.cardDimensions[ev.pricingCard] ?? []).map((d) => <option key={d} value={d}>{d}</option>)}
                      </select>
                    ) : (
                      <span className="font-mono text-accent-text" onClick={() => setEditingCell({ row: i, field: "metric" })}>
                        {metric || <span className="italic text-amber-text">set metric</span>}
                      </span>
                    )}
                  </td>
                  {/* qty (from usageMetrics value) */}
                  <td className={cn("p-1 text-right", editCell, cellOutline(errors, "quantity"))}>
                    {isEditing && editingCell.field === "qty" ? (
                      <input type="number" defaultValue={qty} autoFocus className={cn(inputClass, "text-right font-mono")}
                        onBlur={(e) => { updateQty(i, parseFloat(e.target.value) || 0); setEditingCell(null); }}
                        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
                    ) : (
                      <span className="font-mono text-accent-text" onClick={() => setEditingCell({ row: i, field: "qty" })}>
                        {qty.toLocaleString()}
                      </span>
                    )}
                  </td>
                  <td className="p-1 text-right font-mono font-medium">{costStr}</td>
                  <td className="p-1 text-center">
                    <button className="text-text-muted hover:text-red-text" onClick={() => removeEvent(i)}>
                      <X className="h-3 w-3" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-accent-border bg-accent-ghost/60 px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <input
            className="w-[240px] rounded-sm border border-border-mid bg-bg-surface px-2.5 py-[5px] text-[11px] text-text-primary outline-none placeholder:text-text-muted focus:border-accent-dark focus:ring-2 focus:ring-accent-base/15"
            placeholder="Reason for this addition (required)..."
            value={reason}
            onChange={(e) => onReasonChange(e.target.value)}
          />
          {events.length > 0 && (
            <span className="font-mono text-[10px] text-text-muted">
              Est. total: {formatCostMicros(Math.round(totalCostMicros))}
            </span>
          )}
        </div>
        <button
          className={cn(
            "rounded-full px-5 py-1.5 text-[12px] font-medium text-text-inverse",
            pushResult ? "bg-green" : "bg-accent-base hover:bg-accent-hover",
            !canPush && !isPushing && !pushResult && "cursor-not-allowed opacity-40",
          )}
          onClick={onPush}
          disabled={!canPush || isPushing}
        >
          {isPushing ? "Pushing..." : pushResult ?? "Push to database"}
        </button>
      </div>
    </div>
  );
}
