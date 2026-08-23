import * as React from "react";
import type { UseFormReturn } from "react-hook-form";

import { FormField } from "@/components/shared/form-field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatMicros } from "@/lib/format";
import { PRICING_METHOD_VALUES, RATE_STRUCTURE_VALUES } from "@/lib/vocabulary";
import { cn } from "@/lib/utils";
import type { GroupingFieldDef } from "../api/types";
import {
  exampleChargeMicros,
  toMicros,
  UNIT_QUANTITY_CHOICES,
} from "../lib/pricing-math";
import { pricingMethodLabel } from "@/lib/customer-price";
import { rateStructureLabel } from "../lib/rules";
import { resolveUnitQuantity, type RuleFormValues } from "../lib/schemas";

/**
 * What each method means for the deal, in the console's own words.
 *
 * The catalogue owns the NAME of a value and never the consequence of picking
 * one (ADR-0008 §4): "why choosing this changes the shape of the deal" does not
 * decompose into a concept prefix and a declared value, so it is console copy,
 * exactly as `PRICING_STATUS_EXPLANATIONS` next door is. Total over the
 * generated type, so a method the registry adds tomorrow is a `tsc` failure
 * here rather than an option with no explanation beside it.
 */
const METHOD_CONSEQUENCES = {
  margin_over_cost:
    "A percentage on top of what each call actually cost you. What the customer pays moves when your supplier's price moves.",
  direct_event_price:
    "An amount you set, whatever the call cost you. What the customer pays does not move when your supplier's price does.",
} as const satisfies Record<(typeof PRICING_METHOD_VALUES)[number], string>;

const STRUCTURE_CONSEQUENCES = {
  per_unit: "Charged per unit of the measurement — 1,000 units cost a thousand times one.",
  fixed_component: "Charged once for the event, however many units it measured.",
} as const satisfies Record<(typeof RATE_STRUCTURE_VALUES)[number], string>;

/**
 * The one rule editor — a whole rule, stated.
 *
 * ⚠ **THIS IS THE SURFACE SPEC §21's SECOND OBLIGATION NAMES, AND IT IS THE
 * ONE USUALLY MISSED.** A customer override is a RULE EDITOR, not a number
 * field. The convenience belongs in the UI — create from the inherited rule,
 * method preselected, current value shown — and changing the method stays
 * possible but explicit, because moving a customer from a margin over cost onto
 * a flat price changes the shape of a negotiated deal. A dialog offering only
 * an amount would make that change unreachable while looking complete.
 *
 * ⚠ **ONE COMPONENT FOR BOTH CALLERS, BECAUSE THERE IS ONE RECORD.** A change
 * to a book and a customer's own deal are the same rule declared on two
 * different books — `CustomerOverrideIn` is `BookChangeIn` without the `kind`,
 * and the contract says outright that partial override is not expressible.
 * Two editors would be two chances to disagree about what a rule is, and the
 * one that drifted would be the one a tenant wrote a deal in.
 *
 * ⚠ **THE SLOTS COME FROM THE TENANT'S REGISTRY, ALL OF THEM.** Ruling 15's
 * six-of-ten gap was a published list that stopped being true; a hand-written
 * list here would be the same defect in the console, so this renders whatever
 * the tenant declared — between none and ten.
 *
 * ⚠ **THE TWO SHAPE CHOICES ARE RADIOS AND NOT DROPDOWNS**, which is the
 * explicitness requirement rather than a style preference. A collapsed select
 * shows the option a tenant already has and hides the consequence of the other
 * one; a pair of radios puts both, and what each does to the deal, on the
 * screen at the moment they are deciding. The unit choice below stays a select
 * because picking "per 1M" instead of "per 1K" is an arithmetic detail, not a
 * change to what kind of agreement this is.
 */
export function RuleEditor({
  form,
  groupingFields,
  currency,
  /** Whether the quantity and selectors may still be edited. */
  identityEditable = true,
  /** Shown above the terms where the caller has something to say about them. */
  inheritedNote,
}: {
  form: UseFormReturn<RuleFormValues>;
  groupingFields: readonly GroupingFieldDef[];
  currency: string;
  identityEditable?: boolean;
  inheritedNote?: React.ReactNode;
}) {
  const values = form.watch();
  const errors = form.formState.errors;
  const isFixed = values.rate_structure === "fixed_component";

  return (
    <div className="space-y-4">
      <FormField
        label="Measurement"
        error={errors.measurement_key?.message}
        hint="The quantity this rule prices, e.g. gpt4o_input_tokens."
      >
        {(id) => (
          <Input
            id={id}
            className="font-mono"
            placeholder="gpt4o_input_tokens"
            disabled={!identityEditable}
            {...form.register("measurement_key")}
          />
        )}
      </FormField>

      <fieldset className="space-y-3" disabled={!identityEditable}>
        <legend className="text-[13px] font-medium text-text-primary">
          What this rule applies to
        </legend>
        <p className="text-xs text-muted-foreground">
          Leave a field empty to match anything. The more a rule pins, the
          higher it ranks — specificity decides before the book it sits in does.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FormField label="Provider" error={errors.provider?.message}>
            {(id) => (
              <Input
                id={id}
                className="font-mono"
                placeholder="openai"
                {...form.register("provider")}
              />
            )}
          </FormField>
          <FormField label="Event type" error={errors.event_type?.message}>
            {(id) => (
              <Input
                id={id}
                className="font-mono"
                placeholder="chat.completion"
                {...form.register("event_type")}
              />
            )}
          </FormField>
          <FormField label="Task type" error={errors.task_type?.message}>
            {(id) => (
              <Input id={id} className="font-mono" {...form.register("task_type")} />
            )}
          </FormField>
          <FormField label="Subtask type" error={errors.subtask_type?.message}>
            {(id) => (
              <Input id={id} className="font-mono" {...form.register("subtask_type")} />
            )}
          </FormField>
        </div>
        {groupingFields.length > 0 && (
          <div className="space-y-2">
            <p className="text-[12px] font-medium text-text-primary">
              Your grouping fields
            </p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {groupingFields.map((field) => (
                <FormField key={field.key} label={field.key}>
                  {(id) => (
                    <Input
                      id={id}
                      className="font-mono"
                      value={values.grouping_fields[field.key] ?? ""}
                      onChange={(event) =>
                        form.setValue(
                          "grouping_fields",
                          {
                            ...values.grouping_fields,
                            [field.key]: event.target.value,
                          },
                          { shouldDirty: true },
                        )
                      }
                    />
                  )}
                </FormField>
              ))}
            </div>
          </div>
        )}
      </fieldset>

      <div className="space-y-4 border-t border-border pt-3">
        <p className="text-[13px] font-medium text-text-primary">What it charges</p>
        {inheritedNote}

        <ChoiceGroup
          legend="How the price is derived"
          name="pricing-method"
          value={values.pricing_method}
          options={PRICING_METHOD_VALUES.map((method) => ({
            value: method,
            title: pricingMethodLabel(method),
            description: METHOD_CONSEQUENCES[method],
          }))}
          onChange={(next) =>
            form.setValue("pricing_method", next as RuleFormValues["pricing_method"], {
              shouldDirty: true,
            })
          }
        />

        <ChoiceGroup
          legend="Arithmetic"
          name="rate-structure"
          value={values.rate_structure}
          options={RATE_STRUCTURE_VALUES.map((structure) => ({
            value: structure,
            title: rateStructureLabel(structure),
            description: STRUCTURE_CONSEQUENCES[structure],
          }))}
          onChange={(next) =>
            form.setValue("rate_structure", next as RuleFormValues["rate_structure"], {
              shouldDirty: true,
            })
          }
        />

        {isFixed ? (
          <FormField
            label={`Amount per event (${currency.toUpperCase()})`}
            error={errors.fixed?.message}
          >
            {(id) => <Input id={id} inputMode="decimal" {...form.register("fixed")} />}
          </FormField>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField
              label={`Amount (${currency.toUpperCase()})`}
              error={errors.rate?.message}
            >
              {(id) => <Input id={id} inputMode="decimal" {...form.register("rate")} />}
            </FormField>
            <FormField label="Per">
              {(id) => (
                <Select
                  value={values.unit_choice}
                  onValueChange={(next) =>
                    form.setValue("unit_choice", next as RuleFormValues["unit_choice"], {
                      shouldDirty: true,
                    })
                  }
                >
                  <SelectTrigger id={id} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {UNIT_QUANTITY_CHOICES.map((choice) => (
                      <SelectItem key={choice.value} value={choice.value}>
                        {choice.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </FormField>
            {values.unit_choice === "custom" && (
              <FormField
                label="Units"
                error={errors.custom_unit?.message}
                className="sm:col-span-2"
              >
                {(id) => (
                  <Input id={id} inputMode="numeric" {...form.register("custom_unit")} />
                )}
              </FormField>
            )}
          </div>
        )}

        <RulePreview values={values} currency={currency} />
      </div>
    </div>
  );
}

/** A small radio set: every option, and what picking it means, on the screen. */
function ChoiceGroup({
  legend,
  name,
  value,
  options,
  onChange,
}: {
  legend: string;
  name: string;
  value: string;
  options: ReadonlyArray<{ value: string; title: string; description: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-[13px] font-medium text-text-primary">{legend}</legend>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {options.map((option) => (
          <label
            key={option.value}
            className={cn(
              "flex cursor-pointer gap-2 rounded-lg border px-3 py-2.5 transition-colors",
              option.value === value
                ? "border-border-strong bg-bg-subtle"
                : "border-border hover:bg-bg-subtle/50",
            )}
          >
            <input
              type="radio"
              name={name}
              className="mt-1"
              value={option.value}
              checked={option.value === value}
              onChange={() => onChange(option.value)}
            />
            <span className="min-w-0">
              <span className="block text-[13px] font-medium text-text-primary">
                {option.title}
              </span>
              <span className="mt-0.5 block text-xs text-text-secondary">
                {option.description}
              </span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/**
 * What this rule would charge, worked out on a round number.
 *
 * ⚠ **IT IS SILENT FOR A MARGIN, AND THAT SILENCE IS THE POINT.** A margin's
 * basis is what the supplier charged for the particular call, which is not on
 * this record and is not knowable from a form — so a preview showing a figure
 * here would have to invent the cost it was a margin over. Saying what the
 * percentage is taken over is the whole truth this screen has.
 */
function RulePreview({
  values,
  currency,
}: {
  values: RuleFormValues;
  currency: string;
}) {
  if (values.pricing_method === "margin_over_cost") {
    return (
      <p className="rounded-md bg-bg-subtle px-3 py-2 text-[12px] text-text-secondary">
        This rule charges a margin over what the call cost you, so the amount is
        settled per event from the supplier’s own figure — there is nothing to
        work out here.
      </p>
    );
  }
  // ⚠ THROUGH `toMicros`, NOT AN INLINE `Math.round(x * 1e6)`. The module's own
  // rule is that conversion from user input happens exactly ONCE and in one
  // place; a second copy here is a second rounding rule to keep true, and the
  // preview would eventually disagree with what the form actually sends.
  const unitQuantity = resolveUnitQuantity(values);
  const rate = toMicros(values.rate || "0");
  const fixed = toMicros(values.fixed || "0");
  if (!Number.isFinite(rate) || !Number.isFinite(fixed) || unitQuantity <= 0) {
    return null;
  }
  const units = values.rate_structure === "fixed_component" ? 1 : unitQuantity;
  const charge = exampleChargeMicros(
    {
      rate_structure: values.rate_structure,
      rate_per_unit_micros: rate,
      unit_quantity: unitQuantity,
      fixed_micros: fixed,
    },
    units,
  );
  return (
    <p className="rounded-md bg-bg-subtle px-3 py-2 text-[12px] text-text-secondary">
      {values.rate_structure === "fixed_component"
        ? `Every matching event is charged ${formatMicros(charge, currency)}.`
        : `${units.toLocaleString()} units would be charged ${formatMicros(charge, currency)}.`}
    </p>
  );
}
