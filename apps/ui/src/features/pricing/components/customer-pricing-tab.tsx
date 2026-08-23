import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { DisabledHint } from "@/components/shared/disabled-hint";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { toastSuccess } from "@/lib/mutations";
import {
  useDeclareCustomerOverride,
  useGroupingFields,
  useInheritedRule,
} from "../api/queries";
import type { InheritedPricingRule, InheritedRuleParams } from "../api/types";
import { pricingMethodLabel } from "@/lib/customer-price";
import { microsToUnitString, toMicros, unitChoiceFor } from "../lib/pricing-math";
import { pinnableGroupingFields, rateStructureLabel, ruleAmount } from "../lib/rules";
import { effectiveInstant, scheduleRefusal } from "../lib/schedule";
import {
  blankRule,
  resolveUnitQuantity,
  ruleFormSchema,
  statedGroupingFields,
  type RuleFormValues,
} from "../lib/schemas";
import { EffectiveInstant } from "./effective-instant";
import { RuleEditor } from "./rule-editor";

/**
 * One customer's own pricing rules — the tab #368 and #369 emptied and this
 * commit rebuilds.
 *
 * ⚠ **THE TAB WENT BECAUSE ITS TWO CARDS WERE THE WRONG SHAPE, NOT BECAUSE THE
 * QUESTION WENT AWAY.** It held a book picker, whose assignment record was
 * deleted, and a markup override, whose record and five routes went next. What
 * one named customer is charged is a RULE in their own pricing book now — a
 * record that says which quantity it prices, how it derives a price, and what
 * it charges — so the tab comes back as a rule editor rather than as two
 * number fields.
 *
 * ⚠ **THE STARTING POINT IS THE INHERITED RULE, WHICH IS WHY THIS ASKS BEFORE
 * IT OFFERS.** `GET /pricing/customers/{id}/inherited-rule` answers the same
 * ladder one rung shorter — the customer's own book taken out — so the method
 * and the current value shown cannot drift from what is about to be replaced.
 * A tenant reads what this customer gets today, and the editor opens
 * pre-filled with it.
 *
 * ⚠ **AND NOTHING IS INHERITED INTO THE BODY.** `CustomerOverrideIn` states a
 * whole rule: a field left out takes the rule defaults, never the superseded
 * rule's value. So the editor copies the inherited rule into form state and
 * sends every field — the console does the copying, precisely because the API
 * will not.
 */
export function CustomerPricingTab({ customerId }: { customerId: string }) {
  const isAdmin = useHasRole("admin");
  const groupingFields = useGroupingFields();
  const declare = useDeclareCustomerOverride(customerId);

  const [lookup, setLookup] = React.useState<InheritedRuleParams>({
    measurement_key: "",
    provider: "",
    event_type: "",
  });
  const [editing, setEditing] = React.useState(false);
  const [effectiveLocal, setEffectiveLocal] = React.useState("");

  /**
   * The question as the route takes it: pins the tenant actually stated.
   *
   * ⚠ A BLANK BOX IS "I DID NOT SAY", NOT "THE EMPTY VALUE". Sending `model=`
   * would ask what this customer inherits for an event whose model is
   * literally empty, which is a different and much narrower question — and it
   * would churn the query key on every keystroke into an empty field.
   */
  const question: InheritedRuleParams = React.useMemo(
    () => ({ ...lookup, grouping_fields: statedGroupingFields(lookup.grouping_fields ?? {}) }),
    [lookup],
  );

  const inherited = useInheritedRule(customerId, question);
  const form = useForm<RuleFormValues>({
    resolver: zodResolver(ruleFormSchema),
    defaultValues: blankRule(),
  });

  const declared = pinnableGroupingFields(groupingFields.data ?? []);
  const inheritedRule = inherited.data?.rule ?? null;

  /**
   * Open the editor on what this customer inherits — method preselected,
   * current value shown.
   *
   * ⚠ **AND ON NOTHING WHERE NOTHING IS INHERITED**, which is an ordinary state
   * rather than an error: a quantity no book in play prices falls to the
   * tenant's markup rung, and an override written there starts from a blank
   * rule. Refusing to open the editor would make the one case where a customer
   * has no price at all the one case a tenant cannot fix.
   */
  const startFromInherited = () => {
    declare.reset();
    form.reset(
      inheritedRule
        ? fromInheritedRule(inheritedRule)
        : { ...blankRule(), ...lookupAsRule(question) },
    );
    setEditing(true);
  };

  const onSubmit = (values: RuleFormValues) => {
    declare.mutate(
      {
        measurement_key: values.measurement_key,
        provider: values.provider,
        event_type: values.event_type,
        task_type: values.task_type,
        subtask_type: values.subtask_type,
        grouping_fields: statedGroupingFields(values.grouping_fields),
        pricing_method: values.pricing_method,
        rate_structure: values.rate_structure,
        rate_per_unit_micros: toMicros(values.rate),
        unit_quantity: resolveUnitQuantity(values),
        fixed_micros: toMicros(values.fixed),
        effective_at: effectiveInstant(effectiveLocal),
      },
      {
        onSuccess: () => {
          toastSuccess(
            "Deal declared as a draft",
            "Nothing is charged yet — publish it on this customer's own book to put it in force.",
          );
          setEditing(false);
        },
      },
    );
  };

  return (
    <div className="space-y-4">
      <Card size="sm">
        <CardContent className="space-y-3">
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-text-primary">
              What this customer is charged
            </p>
            <p className="max-w-2xl text-[12px] leading-relaxed text-text-secondary">
              Name the usage you want to look up, and this shows the rule that
              answers for them today with their own rules taken out — the same
              ladder one rung shorter. That is the deal you would be replacing.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <FormField label="Measurement">
              {(id) => (
                <Input
                  id={id}
                  className="font-mono"
                  placeholder="gpt4o_input_tokens"
                  value={lookup.measurement_key}
                  onChange={(event) =>
                    setLookup((current) => ({
                      ...current,
                      measurement_key: event.target.value,
                    }))
                  }
                />
              )}
            </FormField>
            <FormField label="Provider">
              {(id) => (
                <Input
                  id={id}
                  className="font-mono"
                  placeholder="openai"
                  value={lookup.provider ?? ""}
                  onChange={(event) =>
                    setLookup((current) => ({
                      ...current,
                      provider: event.target.value,
                    }))
                  }
                />
              )}
            </FormField>
            <FormField label="Event type">
              {(id) => (
                <Input
                  id={id}
                  className="font-mono"
                  placeholder="chat.completion"
                  value={lookup.event_type ?? ""}
                  onChange={(event) =>
                    setLookup((current) => ({
                      ...current,
                      event_type: event.target.value,
                    }))
                  }
                />
              )}
            </FormField>
          </div>

          {/* ⚠ THE GROUPING VALUES ARE PART OF THE QUESTION, NOT AN EXTRA.
              A rule is identified by the quantity it prices PLUS its selectors,
              and the route takes one `grouping_field=key=value` per pin for
              exactly that reason. A lookup that left them out could only ever
              answer for rules that pin nothing — so a tenant whose catalogue
              prices `gpt-4o` differently from `gpt-4o-mini` would be told they
              inherit nothing, on the very screen they came to check a deal. */}
          {declared.length > 0 && (
            <details className="rounded-md border border-border px-3 py-2">
              <summary className="cursor-pointer text-[12px] text-text-secondary">
                Pin grouping values
              </summary>
              <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
                {declared.map((field) => (
                  <FormField key={field.key} label={field.key}>
                    {(id) => (
                      <Input
                        id={id}
                        className="font-mono"
                        value={lookup.grouping_fields?.[field.key] ?? ""}
                        onChange={(event) =>
                          setLookup((current) => ({
                            ...current,
                            grouping_fields: {
                              ...current.grouping_fields,
                              [field.key]: event.target.value,
                            },
                          }))
                        }
                      />
                    )}
                  </FormField>
                ))}
              </div>
            </details>
          )}

          {lookup.measurement_key === "" ? (
            <p className="text-[12px] text-text-muted">
              Enter a measurement to see what they inherit.
            </p>
          ) : inherited.isLoading ? (
            <Skeleton className="h-12 w-full" />
          ) : inherited.isError ? (
            <ErrorCard
              error={inherited.error}
              onRetry={() => void inherited.refetch()}
              title="Couldn't look up what this customer inherits"
            />
          ) : (
            <InheritedSummary rule={inheritedRule} />
          )}

          {!editing && (
            <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
              <Button
                size="sm"
                disabled={!isAdmin || lookup.measurement_key === "" || inherited.isLoading}
                onClick={startFromInherited}
              >
                {inheritedRule
                  ? "Write their own rule from this"
                  : "Write their own rule"}
              </Button>
            </DisabledHint>
          )}
        </CardContent>
      </Card>

      {editing && (
        <Card size="sm">
          <CardContent>
            <form
              onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
              className="space-y-4"
            >
              <RuleEditor
                form={form}
                groupingFields={declared}
                currency={inheritedRule?.currency ?? "usd"}
                inheritedNote={
                  inheritedRule ? (
                    <p className="rounded-md bg-bg-subtle px-3 py-2 text-[12px] text-text-secondary">
                      Today this customer inherits{" "}
                      <strong className="font-medium text-text-primary">
                        {ruleAmount(inheritedRule, inheritedRule.currency)}
                      </strong>
                      , derived as{" "}
                      <strong className="font-medium text-text-primary">
                        {pricingMethodLabel(inheritedRule.pricing_method)}
                      </strong>
                      . Changing the method below changes the shape of the deal,
                      not just the number — it is allowed, and it is meant to be
                      deliberate.
                    </p>
                  ) : (
                    <p className="rounded-md bg-bg-subtle px-3 py-2 text-[12px] text-text-secondary">
                      Nothing is inherited for this usage, so this rule starts
                      from nothing. Without it, these events fall to your default
                      markup rung.
                    </p>
                  )
                }
              />

              <div className="border-t border-border pt-3">
                <EffectiveInstant
                  label="Date this deal ahead"
                  hint="Within 366 days. Leave it off and it takes effect when you publish it."
                  value={effectiveLocal}
                  onChange={setEffectiveLocal}
                />
              </div>

              {declare.isError && (
                <p className="text-xs text-destructive">
                  {scheduleRefusal(declare.error)}
                </p>
              )}

              <div className="flex items-center gap-2">
                <Button type="submit" size="sm" disabled={declare.isPending}>
                  {declare.isPending ? "Working…" : "Declare this deal"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setEditing(false)}
                  disabled={declare.isPending}
                >
                  Cancel
                </Button>
              </div>
              <p className="text-[12px] text-text-muted">
                Declaring writes no rule. It creates a draft on this customer’s
                own book with its diff; publishing that draft is what puts the
                deal in force.
              </p>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/** What the customer gets today, or that they get nothing. */
function InheritedSummary({ rule }: { rule: InheritedPricingRule | null }) {
  if (rule == null) {
    return (
      <div className="space-y-1 rounded-md border border-border px-3 py-2">
        <Badge variant="outline">Nothing inherited</Badge>
        <p className="text-[12px] text-text-secondary">
          No book in play prices this for them, so it falls to your default
          markup rung. A rule written here starts from nothing rather than from
          an existing deal.
        </p>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-border px-3 py-2">
      <span className="text-[13px] font-medium text-text-primary">
        {ruleAmount(rule, rule.currency)}
      </span>
      <span className="text-[12px] text-text-secondary">
        {rateStructureLabel(rule.rate_structure)}
      </span>
      <span className="text-[12px] text-text-secondary">
        {pricingMethodLabel(rule.pricing_method)}
      </span>
    </div>
  );
}

/**
 * The inherited rule, copied into form state field by field.
 *
 * ⚠ **EVERY FIELD, BECAUSE THE BODY INHERITS NOTHING.** `CustomerOverrideIn`
 * takes the model's own defaults for anything left out — never the superseded
 * rule's value — so a form pre-filled with half of what it inherits would send
 * a rule the tenant never saw. `InheritedPricingRule` exists in exactly this
 * shape so that *create from the inherited rule* is a copy rather than a
 * translation, and this function is the copy.
 */
function fromInheritedRule(rule: InheritedPricingRule): RuleFormValues {
  return {
    measurement_key: rule.measurement_key,
    provider: rule.provider,
    event_type: rule.event_type,
    task_type: rule.task_type,
    subtask_type: rule.subtask_type,
    grouping_fields: { ...(rule.grouping_fields ?? {}) },
    // ⚠ THE METHOD IS PRESELECTED FROM THE RULE AND NOT DEFAULTED. A rule that
    // declares none prices the event's own quantities by its own terms, which
    // is what `direct_event_price` means — the same reading the resolver makes
    // (`pricing_service._priced_by_rules`), rather than a console guess.
    pricing_method: rule.pricing_method ?? "direct_event_price",
    rate_structure: rule.rate_structure,
    rate: microsToUnitString(rule.rate_per_unit_micros),
    unit_choice: unitChoiceFor(rule.unit_quantity),
    custom_unit: String(rule.unit_quantity),
    fixed: microsToUnitString(rule.fixed_micros),
  };
}

/** What the tenant asked about, so a blank rule at least prices that. */
function lookupAsRule(lookup: InheritedRuleParams): Partial<RuleFormValues> {
  return {
    measurement_key: lookup.measurement_key,
    provider: lookup.provider ?? "",
    event_type: lookup.event_type ?? "",
  };
}
