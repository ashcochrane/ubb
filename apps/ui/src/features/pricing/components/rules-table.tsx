import * as React from "react";
import { Layers } from "lucide-react";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate, formatMicros, formatShortDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useGroupingFields, useRules } from "../api/queries";
import { pinnedSelectors, rateStructureLabel, ruleAmount } from "../lib/rules";
import type { AnyBook, GroupingFieldDef, Rule } from "../api/types";

/**
 * A book's rules: active by default, optional full history, optional
 * point-in-time ("as of") view.
 *
 * ⚠ **IT READS AND DOES NOT WRITE, AND THAT IS THE MODEL RATHER THAN A GAP.**
 * The three immediate routes this table used to drive — add a rule, retire one,
 * reprice a set — are deleted (#367, #368), because every change to a book is a
 * declared publish now, read as a diff before it is committed to. The way to
 * change what is in a book is the Changes panel beside this table, and a row
 * action here would be a second mutation surface for an act that has one.
 *
 * ⚠ **HISTORY IS WHERE A REVERSAL READS AS A REVERSAL.** A superseded rule
 * keeps its row and gains an end date, so undoing a change leaves three
 * versions in one lineage with the middle one closed — never two with one
 * missing. That is what makes "we put it up and then we put it back" a thing a
 * tenant can see afterwards rather than a thing they have to remember.
 */
export function RulesTable({ book }: { book: AnyBook }) {
  const [includeHistory, setIncludeHistory] = React.useState(false);
  const [asOfLocal, setAsOfLocal] = React.useState("");
  const asOfIso = React.useMemo(() => {
    if (!asOfLocal) return undefined;
    const parsed = new Date(asOfLocal);
    return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
  }, [asOfLocal]);

  const rules = useRules(book.id, { include_history: includeHistory, as_of: asOfIso });
  const groupingFields = useGroupingFields();
  const declared = groupingFields.data ?? [];

  const pointInTime = asOfIso !== undefined;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <div className="flex items-center gap-2">
          <Switch
            checked={includeHistory}
            onCheckedChange={setIncludeHistory}
            disabled={pointInTime}
            aria-label="Include history"
          />
          <Label className={cn(pointInTime && "opacity-50")}>Include history</Label>
        </div>
        <div className="flex items-center gap-2">
          <Label htmlFor="rules-as-of">As of</Label>
          <Input
            id="rules-as-of"
            type="datetime-local"
            className="h-8 w-[210px] text-[12px]"
            value={asOfLocal}
            onChange={(event) => setAsOfLocal(event.target.value)}
          />
          {pointInTime && (
            <Button variant="ghost" size="sm" onClick={() => setAsOfLocal("")}>
              Clear
            </Button>
          )}
        </div>
      </div>
      <p className="text-[11px] text-text-muted">
        {pointInTime
          ? `Showing the rules that were in force on ${formatDate(asOfIso ?? "")}. The point-in-time view overrides "Include history".`
          : includeHistory
            ? "Showing every version — superseded and retired rules carry an end date and appear muted. Nothing is ever removed, so a change that was put back reads as three versions rather than two."
            : "Showing active rules only. Toggle history to see superseded versions, or pick a moment to see the rules in force then."}
      </p>

      {rules.isInitialLoading ? (
        <Card size="sm" className="p-3">
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        </Card>
      ) : rules.isError ? (
        <ErrorCard
          error={rules.error}
          onRetry={() => void rules.refetch()}
          title="Couldn't load this book's rules"
        />
      ) : rules.rows.length === 0 ? (
        pointInTime || includeHistory ? (
          <EmptyState
            icon={Layers}
            title="No rules for this view"
            description={
              pointInTime
                ? "No rules were in force at that moment. Clear the date to see the current rules."
                : "This book has no rule versions yet."
            }
          />
        ) : (
          <EmptyState
            icon={Layers}
            title="No rules yet"
            description="This book prices nothing yet. Rules arrive by declaring a change and publishing it."
          />
        )
      ) : (
        <Card size="sm" className="gap-0 py-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Measurement</TableHead>
                  <TableHead>Applies to</TableHead>
                  <TableHead>Arithmetic</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead>Per event</TableHead>
                  <TableHead>From</TableHead>
                  <TableHead>Until</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rules.rows.map((rule) => (
                  <RuleRow
                    key={rule.id}
                    rule={rule}
                    currency={rule.currency}
                    declared={declared}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
          <LoadMore
            shownCount={rules.rows.length}
            hasMore={rules.hasMore}
            isFetchingNextPage={rules.isFetchingNextPage}
            onLoadMore={rules.fetchNextPage}
            noun="rules"
          />
        </Card>
      )}
    </div>
  );
}

function RuleRow({
  rule,
  currency,
  declared,
}: {
  rule: Rule;
  currency: string;
  declared: readonly GroupingFieldDef[];
}) {
  const superseded = rule.valid_to != null;
  // ⚠ THE TENANT'S OWN KEYS, ALL TEN SLOTS, AND NEVER A SLOT NUMBER (#277,
  // #366). The list of slots is the tenant's registry rather than a constant
  // here: a hand-written list is what ruling 15's six-of-ten gap was, and
  // writing one in the console would be the same defect one layer out.
  const pins = pinnedSelectors(rule, declared);
  return (
    <TableRow className={cn(superseded && "opacity-55")}>
      <TableCell className="font-mono text-[12px]" title={rule.measurement_key}>
        {rule.measurement_key}
      </TableCell>
      <TableCell>
        <div className="flex max-w-[260px] flex-wrap items-center gap-1">
          {pins.length === 0 ? (
            <span className="text-[11px] text-text-muted">Any event</span>
          ) : (
            pins.map((pin) => (
              <span key={pin.key} className="text-[11px] text-text-secondary">
                <span className="text-text-muted">{pin.key}=</span>
                <span className="font-mono">{pin.value}</span>
              </span>
            ))
          )}
        </div>
      </TableCell>
      <TableCell className="text-[12px]">
        {rateStructureLabel(rule.rate_structure)}
      </TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        {rule.rate_structure === "fixed_component" ? "—" : ruleAmount(rule, currency)}
      </TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        {rule.fixed_micros > 0 ? formatMicros(rule.fixed_micros, currency) : "—"}
      </TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        {formatShortDate(rule.valid_from)}
      </TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        {rule.valid_to ? (
          <span title={formatDate(rule.valid_to)}>{formatShortDate(rule.valid_to)}</span>
        ) : (
          <Badge variant="secondary">Active</Badge>
        )}
      </TableCell>
    </TableRow>
  );
}
