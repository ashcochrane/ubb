import { Link } from "@tanstack/react-router";
import { Users, Plus, ChevronRight, Link2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { BoolBadge } from "@/components/shared/status-badge";
import { CopyField } from "@/components/shared/data-states";
import { LoadingRows, ErrorInline } from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { formatShortDate } from "@/lib/format";
import { useReferrers } from "../api/queries";
import { RegisterReferrerDialog } from "./register-referrer-dialog";
import { AttributeDialog } from "./attribute-dialog";

export function ReferrersTab() {
  const pager = useReferrers();

  const actions = (
    <div className="flex items-center gap-2">
      <AttributeDialog
        trigger={
          <Button variant="outline" size="sm">
            <Link2 />
            Attribute referral
          </Button>
        }
      />
      <RegisterReferrerDialog
        trigger={
          <Button size="sm">
            <Plus />
            Register referrer
          </Button>
        }
      />
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">{actions}</div>

      {pager.isLoading ? (
        <LoadingRows />
      ) : pager.isError ? (
        <ErrorInline error={pager.error} onRetry={pager.refetch} />
      ) : pager.items.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No referrers yet"
          description="Register a customer as a referrer to give them a shareable code and link."
        />
      ) : (
        <div className="space-y-3">
          <div className="rounded-xl bg-card ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Referral code</TableHead>
                  <TableHead>Customer</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Registered</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {pager.items.map((ref) => (
                  <TableRow key={ref.id}>
                    <TableCell className="max-w-[16rem]">
                      <CopyField value={ref.referral_code} />
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      <Link
                        to="/referrals/$customerId"
                        params={{ customerId: ref.customer_id }}
                        className="hover:underline"
                      >
                        {ref.customer_id}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <BoolBadge
                        value={ref.is_active}
                        trueLabel="Active"
                        falseLabel="Inactive"
                      />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatShortDate(ref.created_at)}
                    </TableCell>
                    <TableCell>
                      <Link
                        to="/referrals/$customerId"
                        params={{ customerId: ref.customer_id }}
                      >
                        <ChevronRight className="size-4 text-muted-foreground" />
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <CursorPagerControls pager={pager} />
        </div>
      )}
    </div>
  );
}
