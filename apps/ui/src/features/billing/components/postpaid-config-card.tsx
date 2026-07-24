import { useState } from "react";

import { problemMessage } from "@/api/problem";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { toastSuccess } from "@/lib/mutations";

import { usePostpaidConfig, useSavePostpaidConfig } from "../api/queries";
import type { PostpaidConfig } from "../api/types";
import {
  buildPostpaidPayload,
  postpaidToFormState,
  type GroupByMode,
} from "../lib/billing-forms";
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
  const [mode, setMode] = useState<GroupByMode>(initial.mode);
  const [tagKey, setTagKey] = useState(initial.tagKey);
  const [consolidate, setConsolidate] = useState(initial.consolidate);
  const mutation = useSavePostpaidConfig();

  const tagKeyMissing = mode === "tag" && tagKey.trim() === "";
  const payload = tagKeyMissing
    ? null
    : buildPostpaidPayload(current, { mode, tagKey, consolidate });

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
          error={tagKeyMissing ? "Enter the tag key to group by" : undefined}
        >
          {(id) => (
            <div className="flex flex-wrap items-center gap-2">
              <Select
                value={mode}
                onValueChange={(v) => {
                  if (v === "single" || v === "product" || v === "tag") setMode(v);
                }}
              >
                <SelectTrigger id={id} className="w-[240px]" disabled={!isAdmin}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="single">Single line — one total</SelectItem>
                  <SelectItem value="product">One line per product</SelectItem>
                  <SelectItem value="tag">One line per tag value</SelectItem>
                </SelectContent>
              </Select>
              {mode === "tag" && (
                <Input
                  value={tagKey}
                  onChange={(e) => setTagKey(e.target.value)}
                  placeholder="Tag key, e.g. seat"
                  aria-label="Tag key"
                  className="w-[160px]"
                />
              )}
            </div>
          )}
        </FormField>

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
        <Button onClick={save} disabled={!isAdmin || payload === null || mutation.isPending}>
          {mutation.isPending ? "Working…" : "Save settings"}
        </Button>
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
