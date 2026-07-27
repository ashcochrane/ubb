import { useState } from "react";
import { ChevronRight } from "lucide-react";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useHasRole } from "@/hooks/use-current-role";
import { formatDate } from "@/lib/format";

import { useReferrers } from "../api/queries";
import { looseDate } from "../lib/dates";
import { RegisterReferrerDialog } from "./register-referrer-dialog";

export function ReferrersSection({
  onOpenReferrer,
}: {
  onOpenReferrer: (customerId: string) => void;
}) {
  const referrers = useReferrers();
  const [registerOpen, setRegisterOpen] = useState(false);
  const canWrite = useHasRole("write");

  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle>Referrers</CardTitle>
        <CardDescription>
          Customers with a referral code and link they can share. Open one for its referrals and
          reward history.
        </CardDescription>
        <CardAction>
          <Button
            size="sm"
            onClick={() => setRegisterOpen(true)}
            disabled={!canWrite}
            title={canWrite ? undefined : "Requires the Write role"}
          >
            Register referrer
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="px-0">
        {referrers.isInitialLoading ? (
          <div className="space-y-2 px-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-8 w-full" />
            ))}
          </div>
        ) : referrers.isError ? (
          <ErrorCard
            error={referrers.error}
            onRetry={() => void referrers.refetch()}
            title="Couldn't load referrers"
            className="mx-4"
          />
        ) : referrers.rows.length === 0 ? (
          <EmptyState
            title="No referrers yet"
            description="Register a customer as a referrer to mint their shareable code and link token."
            action={{ label: "Register referrer", onClick: () => setRegisterOpen(true) }}
            className="mx-4"
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead>Code</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {referrers.rows.map((referrer) => (
                  <TableRow
                    key={referrer.id}
                    className="cursor-pointer"
                    onClick={() => onOpenReferrer(referrer.customer_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") onOpenReferrer(referrer.customer_id);
                    }}
                    tabIndex={0}
                    role="link"
                    aria-label={`Open referrer ${referrer.referral_code}`}
                  >
                    <TableCell
                      className="max-w-[240px] truncate font-mono text-[12px]"
                      title={referrer.customer_id}
                    >
                      {referrer.customer_id}
                    </TableCell>
                    <TableCell className="font-mono text-[12px]">
                      {referrer.referral_code}
                    </TableCell>
                    <TableCell>
                      {/* App-wide badge rule: Active = secondary, dormant = outline. */}
                      <Badge variant={referrer.is_active ? "secondary" : "outline"}>
                        {referrer.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-text-secondary">
                      {looseDate(referrer.created_at, formatDate)}
                    </TableCell>
                    <TableCell>
                      <ChevronRight className="h-4 w-4 text-text-muted" strokeWidth={1.5} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <LoadMore
              shownCount={referrers.rows.length}
              hasMore={referrers.hasMore}
              isFetchingNextPage={referrers.isFetchingNextPage}
              onLoadMore={referrers.fetchNextPage}
              noun="referrers"
            />
          </>
        )}
      </CardContent>
      <RegisterReferrerDialog open={registerOpen} onOpenChange={setRegisterOpen} />
    </Card>
  );
}
