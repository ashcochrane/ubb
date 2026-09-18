// How a customer's usage is laid out on the invoice UBB pushes at period close
// (#508; slice 7 §6, §11).
//
// ⚠ **THE AXIS IS CHOSEN FROM THE TENANT'S OWN DISCOVERY CONTRACT, AND THAT IS
// WHAT REPLACED A FREE-TEXT BOX.** Until #503 this form offered three shapes —
// one total, one line per product, one line per value of a key the tenant
// TYPED — and posted whatever string it composed. ADR-0005 names that key the
// sharpest of its three free-text hatches and the only one a paying customer
// reads: *"an unbounded free-text key driving invoice line labels is how a
// 5,000-line invoice happens."* The list is now computed per tenant, the kind
// of each axis stays visible because a field and a rollup have different
// cardinality and cost (§6), and the server refuses a word it did not offer.
//
// ⚠ **AND THE LIST HERE IS NARROWER THAN A CHART'S, FROM THE SAME CONTRACT.**
// An axis resolving at the measurement grain is analytics-only — an invoice
// line is money and UBB holds none at that grain — so the rows carry
// `supported_surfaces` and this picker reads only those naming this one.
// Offering the rest would put an axis in a picker whose request the server
// refuses at save.

import { useState } from "react";

import { problemMessage } from "@/api/problem";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import {
  GroupingAxisLabel,
  SelectedGroupingAxis,
} from "@/components/shared/grouping-axis-label";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useHasRole } from "@/hooks/use-current-role";
import {
  INVOICE_LINES_SURFACE,
  optionsForSurface,
  useGroupingOptions,
} from "@/hooks/use-grouping-options";
import { toastSuccess } from "@/lib/mutations";

import { usePostpaidConfig, useSavePostpaidConfig } from "../api/queries";
import type { PostpaidConfig } from "../api/types";
import { buildPostpaidPayload, postpaidToFormState } from "../lib/billing-forms";
import {
  cardinalityWarning,
  isRollup,
  ROLLUP_RECLASSIFIES_HISTORY,
  SINGLE_LINE,
  SINGLE_LINE_LABEL,
} from "../lib/invoice-lines";
import { SectionCard } from "./section-card";

export function PostpaidConfigCard() {
  const query = usePostpaidConfig(true);
  const isAdmin = useHasRole("admin");

  return (
    <SectionCard
      title="Postpaid invoicing"
      description="How usage is laid out on the Stripe invoices pushed at period close."
    >
      {query.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-9 w-full max-w-sm" />
          <Skeleton className="h-9 w-full max-w-sm" />
        </div>
      ) : query.isError ? (
        <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data ? (
        <PostpaidForm current={query.data} isAdmin={isAdmin} />
      ) : null}
    </SectionCard>
  );
}

function PostpaidForm({ current, isAdmin }: { current: PostpaidConfig; isAdmin: boolean }) {
  const initial = postpaidToFormState(current);
  const [axis, setAxis] = useState(initial.axis);
  const [consolidate, setConsolidate] = useState(initial.consolidate);
  const mutation = useSavePostpaidConfig();

  // ⚠ NO SKELETON AND NO ERROR CARD ON THE AXIS LIST, matching the chart
  // picker's choice for the same reason: while the discovery contract is in
  // flight the form offers the single line, and what is already stored still
  // renders — through the open-set rule, which is the honest answer for an
  // axis this build cannot look up rather than a blank where a value is.
  const axes = optionsForSurface(useGroupingOptions().data, INVOICE_LINES_SURFACE);
  const chosen = axes.find((option) => option.key === axis);
  const warning = cardinalityWarning(chosen);

  const payload = buildPostpaidPayload(current, { axis, consolidate });

  const save = () => {
    if (!payload) return;
    mutation.mutate(payload, {
      onSuccess: () => toastSuccess("Invoicing settings saved"),
    });
  };

  return (
    <div className="max-w-xl space-y-4">
      <fieldset disabled={!isAdmin} className="space-y-4">
        <FormField
          label="Usage line items"
          hint="How a customer's usage is split into invoice lines."
        >
          {(id) => (
            <Select
              value={axis}
              onValueChange={(value) => {
                if (typeof value === "string") setAxis(value);
              }}
            >
              <SelectTrigger id={id} className="w-[280px]" disabled={!isAdmin}>
                {/* RENDERED, NOT ECHOED — left alone this trigger prints the raw
                    request word, so a tenant would read `rollup:event_category`
                    as the description of their own invoice layout. */}
                <SelectValue>
                  {(value: string) => (
                    <SelectedGroupingAxis
                      axes={axes}
                      value={value}
                      none={{ value: SINGLE_LINE, label: SINGLE_LINE_LABEL }}
                    />
                  )}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={SINGLE_LINE}>{SINGLE_LINE_LABEL}</SelectItem>
                {axes.map((option) => (
                  <SelectItem key={option.key} value={option.key}>
                    <GroupingAxisLabel option={option} />
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </FormField>

        {/* ⚠ **AT CONFIGURATION TIME, WHICH IS THE ONLY MOMENT IT IS ANY USE.**
            Warning at invoice time would be worse than useless: the first
            anyone hears of it is a 5,000-line invoice that has already reached
            a customer. The moment a tenant can still act on it is the moment
            they choose the axis, so it renders beside the choice — as a
            warning and never a refusal, because the cap is a bound the tenant
            declared on their own axis rather than an invariant UBB may decline
            to bill against. */}
        {warning && (
          <p data-invoice-warning="cardinality" className="text-[12px] text-text-secondary">
            {warning}
          </p>
        )}

        {/* The behaviour a rollup has and a field does not, said where the
            rollup is chosen (§6). */}
        {isRollup(chosen) && (
          <p data-invoice-note="rollup-reclassifies" className="text-[12px] text-text-secondary">
            {ROLLUP_RECLASSIFIES_HISTORY}
          </p>
        )}

        <label className="flex items-start gap-3">
          <Switch
            checked={consolidate}
            onCheckedChange={(checked) => setConsolidate(checked)}
            disabled={!isAdmin}
          />
          <span className="text-[13px]">
            <span className="font-medium text-text-primary">
              Consolidate with the subscription invoice
            </span>
            <span className="mt-0.5 block text-[12px] text-text-secondary">
              Add usage lines to the customer's subscription invoice instead of issuing a
              separate usage invoice.
            </span>
          </span>
        </label>
      </fieldset>

      <div className="flex flex-wrap items-center gap-3">
        <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
          <Button onClick={save} disabled={!isAdmin || payload === null || mutation.isPending}>
            {mutation.isPending ? "Working…" : "Save settings"}
          </Button>
        </DisabledHint>
        <p className="text-[11px] text-text-muted">
          Only settings you change are saved — everything else keeps its stored value.
        </p>
      </div>
      {mutation.isError && (
        <p className="text-xs text-destructive">{problemMessage(mutation.error)}</p>
      )}
      {!isAdmin && (
        <p className="text-[11px] text-text-muted">
          Changing invoicing settings needs the Admin role.
        </p>
      )}
    </div>
  );
}
