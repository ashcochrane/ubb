import { Link } from "@tanstack/react-router";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useTenantConfig, useTenantCurrency } from "@/hooks/use-tenant-config";
import { tenantDefinedLabel } from "@/lib/localisation";

import type { KindOfWork } from "../api/types";
import {
  altitudeLabel,
  describeCeiling,
  describeDuration,
  effectiveCeiling,
  pricingModeLabel,
  sortedKinds,
} from "../lib/kinds";

/**
 * The kinds of work a workspace has declared — the front door of the Tasks
 * tab (#423, spec §25 Q2): how the business sells, not a log of what ran.
 *
 * Every row is a LINK to the kind's own page, because a kind of work is a
 * routed object a colleague can be sent to (Q1). The key renders as the tenant
 * spelled it — `task_type_key` is theirs, so there are no words of UBB's to
 * put on it.
 */
export function KindsTable({ kinds }: { kinds: readonly KindOfWork[] }) {
  const { data: config } = useTenantConfig();
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
                  {describeCeiling(effectiveCeiling(kind, config), currency)}
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
