import { useState } from "react";
import { Check, X, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
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

function validate(r: StagedEvent, opts: EventFilterOptions): ValidationError[] {
  const e: ValidationError[] = [];
  if (!r.timestamp) e.push({ field: "timestamp", message: "Date required" });
  if (!r.customerKey) e.push({ field: "customerKey", message: "Customer required" });
  else if (!opts.customers.some((c) => c.key === r.customerKey))
    e.push({ field: "customerKey", message: `Unknown: ${r.customerKey}`, warning: true });
  if (!r.cardKey) e.push({ field: "cardKey", message: "Card required" });
  else if (!opts.cards.some((c) => c.key === r.cardKey))
    e.push({ field: "cardKey", message: `Unknown card: ${r.cardKey}` });
  if (!r.dimension) e.push({ field: "dimension", message: "Dimension required" });
  else if (r.cardKey && opts.cardDimensions[r.cardKey] && !opts.cardDimensions[r.cardKey]!.includes(r.dimension))
    e.push({ field: "dimension", message: `${r.dimension} not on ${r.cardKey}` });
  if (!r.quantity || r.quantity <= 0) e.push({ field: "quantity", message: "Qty must be > 0" });
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
  const [editingCell, setEditingCell] = useState<{ row: number; field: keyof StagedEvent } | null>(null);

  const allValidations = events.map((ev) => validate(ev, filterOptions));
  const errorCount = allValidations.filter((v) => v.some((e) => !e.warning)).length;
  const canPush = events.length > 0 && errorCount === 0 && reason.trim().length > 0;

  let totalCost = 0;
  for (const ev of events) {
    const up = filterOptions.dimensionPrices[ev.dimension] ?? 0;
    totalCost += ev.quantity * up;
  }

  function updateEvent(idx: number, partial: Partial<StagedEvent>) {
    const updated = [...events];
    updated[idx] = { ...updated[idx]!, ...partial };
    if ("cardKey" in partial && partial.cardKey) {
      const dims = filterOptions.cardDimensions[partial.cardKey];
      updated[idx]!.dimension = dims?.length === 1 ? dims[0]! : "";
    }
    onEventsChange(updated);
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
        <table className="w-full min-w-[780px] border-collapse text-[10px]">
          <thead>
            <tr>
              {["", "TIME", "CUSTOMER", "GROUP", "CARD", "DIMENSION", "QTY", "UNIT PRICE", "COST", ""].map((h, i) => (
                <th key={i} className={cn(
                  "sticky top-0 z-[2] border-b border-border bg-bg-subtle p-1.5 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted",
                  i === 0 && "w-[22px]",
                  i === 1 && "w-[88px] text-left",
                  i === 2 && "w-[82px] text-left",
                  i === 3 && "w-[82px] text-left",
                  i === 4 && "w-[82px] text-left",
                  i === 5 && "w-[78px] text-left",
                  i === 6 && "w-[50px] text-right",
                  i === 7 && "w-[80px] text-right",
                  i === 8 && "w-[56px] text-right",
                  i === 9 && "w-[24px]",
                )}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.map((ev, i) => {
              const errors = allValidations[i]!;
              const up = filterOptions.dimensionPrices[ev.dimension] ?? 0;
              const cost = ev.quantity * up;
              const upStr = up ? up.toFixed(10).replace(/0+$/, "").replace(/\.$/, ".0") : "\u2014";
              const costStr = up && ev.quantity ? `$${cost.toFixed(6)}` : "\u2014";
              const isEditing = editingCell?.row === i;

              return (
                <tr key={i} className="border-b border-bg-subtle last:border-0 hover:bg-bg-page">
                  <td className="p-1 text-center"><ValidationIcon errors={errors} /></td>
                  <td className={cn("p-1", editCell, cellOutline(errors, "timestamp"))}>
                    {isEditing && editingCell.field === "timestamp" ? (
                      <input type="date" defaultValue={ev.timestamp} autoFocus className={cn(inputClass, "font-mono")}
                        onBlur={(e) => { updateEvent(i, { timestamp: e.target.value }); setEditingCell(null); }}
                        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
                    ) : (
                      <span className="font-mono text-accent-text" onClick={() => setEditingCell({ row: i, field: "timestamp" })}>
                        {ev.timestamp || <span className="font-sans italic text-amber-text">set date</span>}
                      </span>
                    )}
                  </td>
                  <td className={cn("p-1", editCell, cellOutline(errors, "customerKey"))}>
                    {isEditing && editingCell.field === "customerKey" ? (
                      <select defaultValue={ev.customerKey} autoFocus className={inputClass}
                        onBlur={(e) => { updateEvent(i, { customerKey: e.target.value }); setEditingCell(null); }}
                        onChange={(e) => { updateEvent(i, { customerKey: e.target.value }); setEditingCell(null); }}>
                        <option value="">Select...</option>
                        {filterOptions.customers.map((c) => <option key={c.key} value={c.key}>{c.key}</option>)}
                      </select>
                    ) : (
                      <span className="font-medium text-accent-text" onClick={() => setEditingCell({ row: i, field: "customerKey" })}>
                        {ev.customerKey || <span className="font-normal italic text-amber-text">set customer</span>}
                      </span>
                    )}
                  </td>
                  <td className={cn("p-1", editCell)}>
                    {isEditing && editingCell.field === "groupKey" ? (
                      <select defaultValue={ev.groupKey} autoFocus className={inputClass}
                        onBlur={(e) => { updateEvent(i, { groupKey: e.target.value }); setEditingCell(null); }}
                        onChange={(e) => { updateEvent(i, { groupKey: e.target.value }); setEditingCell(null); }}>
                        <option value="">(none)</option>
                        {filterOptions.groups.map((g) => <option key={g.key} value={g.key}>{g.key}</option>)}
                      </select>
                    ) : (
                      <span className="font-mono text-accent-text" onClick={() => setEditingCell({ row: i, field: "groupKey" })}>
                        {ev.groupKey || <span className="text-text-muted">&mdash;</span>}
                      </span>
                    )}
                  </td>
                  <td className={cn("p-1", editCell, cellOutline(errors, "cardKey"))}>
                    {isEditing && editingCell.field === "cardKey" ? (
                      <select defaultValue={ev.cardKey} autoFocus className={inputClass}
                        onBlur={(e) => { updateEvent(i, { cardKey: e.target.value }); setEditingCell(null); }}
                        onChange={(e) => { updateEvent(i, { cardKey: e.target.value }); setEditingCell(null); }}>
                        <option value="">Select...</option>
                        {filterOptions.cards.map((c) => <option key={c.key} value={c.key}>{c.key}</option>)}
                      </select>
                    ) : (
                      <span className="text-accent-text" onClick={() => setEditingCell({ row: i, field: "cardKey" })}>
                        {ev.cardKey}
                      </span>
                    )}
                  </td>
                  <td className={cn("p-1", editCell, cellOutline(errors, "dimension"))}>
                    {isEditing && editingCell.field === "dimension" ? (
                      <select defaultValue={ev.dimension} autoFocus className={inputClass}
                        onBlur={(e) => { updateEvent(i, { dimension: e.target.value }); setEditingCell(null); }}
                        onChange={(e) => { updateEvent(i, { dimension: e.target.value }); setEditingCell(null); }}>
                        <option value="">Select...</option>
                        {(filterOptions.cardDimensions[ev.cardKey] ?? []).map((d) => <option key={d} value={d}>{d}</option>)}
                      </select>
                    ) : (
                      <span className="font-mono text-accent-text" onClick={() => setEditingCell({ row: i, field: "dimension" })}>
                        {ev.dimension}
                      </span>
                    )}
                  </td>
                  <td className={cn("p-1 text-right", editCell, cellOutline(errors, "quantity"))}>
                    {isEditing && editingCell.field === "quantity" ? (
                      <input type="number" defaultValue={ev.quantity} autoFocus className={cn(inputClass, "text-right font-mono")}
                        onBlur={(e) => { updateEvent(i, { quantity: parseFloat(e.target.value) || 0 }); setEditingCell(null); }}
                        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
                    ) : (
                      <span className="font-mono text-accent-text" onClick={() => setEditingCell({ row: i, field: "quantity" })}>
                        {ev.quantity.toLocaleString()}
                      </span>
                    )}
                  </td>
                  <td className="p-1 text-right font-mono text-[9px] text-text-muted">{upStr}</td>
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
              Total: ${totalCost.toFixed(4)}
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
