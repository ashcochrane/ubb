import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { pricingModelLabel } from "@/lib/labels";
import type { Rate } from "../api/types";
import { UNIT_QUANTITY_CHOICES, type RateShape, type UnitChoice } from "../lib/pricing-math";
import { shapeSummary, type RowEdit } from "../lib/publish-edits";

/** One editable rate row inside the publish dialog, with an old → new summary. */
export function PublishRow({
  rate,
  edit,
  next,
  changed,
  invalid,
  currency,
  onEdit,
}: {
  rate: Rate;
  edit: RowEdit;
  next: RateShape | null;
  changed: boolean;
  invalid: boolean;
  currency: string;
  onEdit: (edit: RowEdit) => void;
}) {
  return (
    <div
      className={`rounded-lg border px-3 py-2.5 ${invalid ? "border-destructive" : changed ? "border-border-strong" : "border-border"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <span className="font-mono text-[12px] font-medium text-text-primary">
            {rate.metric_name}
          </span>
          <span className="ml-2 text-[11px] text-text-muted">
            {[rate.provider, rate.event_type].filter(Boolean).join(" · ")}
          </span>
        </div>
        {changed && <Badge variant="secondary">Changed</Badge>}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Select
          value={edit.pricing_model}
          onValueChange={(model) =>
            onEdit({ ...edit, pricing_model: model === "flat" ? "flat" : "per_unit" })
          }
        >
          <SelectTrigger
            className="w-full"
            aria-label={`Pricing model for ${rate.metric_name}`}
          >
            {pricingModelLabel(edit.pricing_model)}
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="per_unit">{pricingModelLabel("per_unit")}</SelectItem>
            <SelectItem value="flat">{pricingModelLabel("flat")}</SelectItem>
          </SelectContent>
        </Select>
        <Input
          inputMode="decimal"
          value={edit.rate}
          disabled={edit.pricing_model === "flat"}
          onChange={(event) => onEdit({ ...edit, rate: event.target.value })}
          aria-label={`Rate for ${rate.metric_name} (${currency.toUpperCase()})`}
        />
        <div className="flex flex-col gap-1">
          <Select
            value={edit.unit_choice}
            onValueChange={(choice) =>
              onEdit({ ...edit, unit_choice: choice as UnitChoice })
            }
          >
            <SelectTrigger
              className="w-full"
              aria-label={`Unit quantity for ${rate.metric_name}`}
              disabled={edit.pricing_model === "flat"}
            >
              {UNIT_QUANTITY_CHOICES.find((c) => c.value === edit.unit_choice)?.label ??
                "per unit"}
            </SelectTrigger>
            <SelectContent>
              {UNIT_QUANTITY_CHOICES.map((choice) => (
                <SelectItem key={choice.value} value={choice.value}>
                  {choice.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {edit.unit_choice === "custom" && edit.pricing_model !== "flat" && (
            <Input
              inputMode="numeric"
              placeholder="Units"
              value={edit.custom_unit}
              onChange={(event) => onEdit({ ...edit, custom_unit: event.target.value })}
              aria-label={`Custom unit quantity for ${rate.metric_name}`}
            />
          )}
        </div>
        <Input
          inputMode="decimal"
          value={edit.fixed}
          onChange={(event) => onEdit({ ...edit, fixed: event.target.value })}
          aria-label={`Fixed amount for ${rate.metric_name} (${currency.toUpperCase()})`}
        />
      </div>
      {changed && next && (
        <p className="mt-2 text-[12px] text-text-secondary">
          {shapeSummary(rate, currency)}
          <span className="mx-1.5 text-text-muted">→</span>
          <span className="font-medium text-text-primary">
            {shapeSummary(next, currency)}
          </span>
        </p>
      )}
      {invalid && (
        <p className="mt-2 text-[12px] text-destructive">
          Enter a non-negative amount (and a whole-number unit quantity).
        </p>
      )}
    </div>
  );
}
