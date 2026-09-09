import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { DisabledHint } from "@/components/shared/disabled-hint";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantConfig, useTenantCurrency } from "@/hooks/use-tenant-config";
import { tenantDefinedLabel } from "@/lib/localisation";
import { pricingModeLabel } from "@/lib/pricing-mode";

import type { KindOfWork } from "../api/types";
import {
  altitudeLabel,
  declaredCeiling,
  describeCeiling,
  describeDuration,
  describeUndeclaredWorkCeiling,
  sortedKinds,
  undeclaredWorkCeiling,
} from "../lib/kinds";
import { UndeclaredWorkDialog } from "./undeclared-work-dialog";

/** What the standing row is called, on the page and in its tests. */
export const UNDECLARED_WORK_LABEL = "Work with no declared kind";

/**
 * The kinds of work a workspace has declared — the front door of the Tasks
 * tab (#423, spec §25 Q2): how the business sells, not a log of what ran.
 *
 * Every row is a LINK to the kind's own page, because a kind of work is a
 * routed object a colleague can be sent to (Q1). The key renders as the tenant
 * spelled it — `task_type_key` is theirs, so there are no words of UBB's to
 * put on it.
 *
 * THE FIRST ROW STANDS FOR WORK WITH NO DECLARED KIND (#453, slice 6 §2,
 * §18). The workspace's two default ceilings — one per altitude — apply to
 * exactly that work and to nothing else: a declared kind of work states its
 * own ceiling or declares itself uncapped, and never inherits these. So they
 * are shown beside the declared kinds, as the ceiling of the one "kind" a
 * tenant can never declare, and edited here rather than on the settings page,
 * where a ceiling is not a billing knob (#141 §7). "No ceiling" on this row is
 * an absence, never "Uncapped" — that word is a declaration's.
 */
export function KindsTable({ kinds }: { kinds: readonly KindOfWork[] }) {
  const currency = useTenantCurrency();
  return (
    <Card size="sm" className="gap-0 py-0">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Kind of work</TableHead>
              <TableHead>Altitude</TableHead>
              <TableHead>Sold</TableHead>
              <TableHead>Ceiling</TableHead>
              <TableHead>Silence window</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <UndeclaredWorkRow currency={currency} />
            {sortedKinds(kinds).map((kind) => (
              <TableRow key={`${kind.kind}:${kind.key}`}>
                <TableCell>
                  <Link
                    to="/tasks/kinds/$key"
                    params={{ key: kind.key }}
                    className="font-mono text-[12px] font-medium text-text-primary underline-offset-2 hover:underline"
                  >
                    {tenantDefinedLabel(kind.key)}
                  </Link>
                </TableCell>
                <TableCell className="text-[12px]">{altitudeLabel(kind.kind)}</TableCell>
                <TableCell className="text-[12px]">
                  {pricingModeLabel(kind.pricing_mode)}
                </TableCell>
                <TableCell className="text-[12px]">
                  {describeCeiling(declaredCeiling(kind), currency)}
                </TableCell>
                <TableCell className="text-[12px]">
                  {describeDuration(kind.silence_window_seconds) ?? "Workspace default"}
                </TableCell>
                <TableCell>
                  {kind.retired ? (
                    <Badge variant="secondary">Retired</Badge>
                  ) : (
                    <Badge variant="outline">Live</Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}

/**
 * The standing row: the workspace's two default ceilings for work started
 * with no declared kind, one per altitude, editable in place (Admin).
 *
 * Undeclared work is priced per event — an untyped unit has no declaration
 * that could have said otherwise — and runs under the workspace's own silence
 * window, so those two cells say what the row's runs actually get.
 */
function UndeclaredWorkRow({ currency }: { currency: string }) {
  const { data: config } = useTenantConfig();
  const isAdmin = useHasRole("admin");
  const [editing, setEditing] = useState(false);
  const wholeWork = undeclaredWorkCeiling(config, "task");
  const containedWork = undeclaredWorkCeiling(config, "subtask");
  return (
    <TableRow data-testid="undeclared-work-row" className="bg-bg-subtle/40">
      <TableCell>
        <span className="text-[12px] font-medium italic text-text-secondary">
          {UNDECLARED_WORK_LABEL}
        </span>
      </TableCell>
      <TableCell className="text-[12px]">
        {altitudeLabel("task")} · {altitudeLabel("subtask")}
      </TableCell>
      <TableCell className="text-[12px]">{pricingModeLabel("event_priced")}</TableCell>
      <TableCell className="text-[12px]">
        <span className="block">
          <span className="text-text-secondary">{altitudeLabel("task")}: </span>
          {describeUndeclaredWorkCeiling(wholeWork, currency)}
        </span>
        <span className="block">
          <span className="text-text-secondary">{altitudeLabel("subtask")}: </span>
          {describeUndeclaredWorkCeiling(containedWork, currency)}
        </span>
      </TableCell>
      <TableCell className="text-[12px]">Workspace default</TableCell>
      <TableCell>
        <span className="inline-flex items-center gap-2">
          <Badge variant="outline">Standing</Badge>
          <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setEditing(true)}
              disabled={!isAdmin || config === undefined}
            >
              Edit default ceilings
            </Button>
          </DisabledHint>
        </span>
        {config !== undefined && (
          <UndeclaredWorkDialog open={editing} onOpenChange={setEditing} config={config} />
        )}
      </TableCell>
    </TableRow>
  );
}
