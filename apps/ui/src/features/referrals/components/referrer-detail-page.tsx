import { useNavigate } from "@tanstack/react-router";
import { ArrowLeft, ScrollText, Ban } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { StatCard } from "@/components/shared/stat-card";
import {
  QueryState,
  Section,
  DetailGrid,
  DetailRow,
  CopyField,
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { StatusBadge, BoolBadge } from "@/components/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { formatDate, formatShortDate, formatMicros, formatEventCount } from "@/lib/format";
import { useAuth } from "@/features/auth/hooks/use-auth";
import {
  useReferrer,
  useReferrerEarnings,
  useReferrerReferrals,
  useRevokeReferral,
} from "../api/queries";
import { ReferralLedgerDialog } from "./referral-ledger-dialog";

export function ReferrerDetailPage({ customerId }: { customerId: string }) {
  const navigate = useNavigate();
  const referrer = useReferrer(customerId);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Referrer"
        actions={
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate({ to: "/referrals" })}
          >
            <ArrowLeft />
            Back
          </Button>
        }
      />

      <QueryState
        query={referrer}
        isEmpty={(r) => r == null}
        empty={{
          title: "Referrer not found",
          description: "This customer may not be registered as a referrer.",
        }}
      >
        {(ref) => (
          <div className="space-y-6">
            <Section title="Referrer">
              <DetailGrid>
                <DetailRow label="Customer ID">
                  <span className="font-mono text-xs">{ref.customer_id}</span>
                </DetailRow>
                <DetailRow label="Status">
                  <BoolBadge
                    value={ref.is_active}
                    trueLabel="Active"
                    falseLabel="Inactive"
                  />
                </DetailRow>
                <DetailRow label="Referral code">
                  <CopyField value={ref.referral_code} />
                </DetailRow>
                <DetailRow label="Referral link token">
                  <CopyField value={ref.referral_link_token} />
                </DetailRow>
                <DetailRow label="Registered">
                  {formatDate(ref.created_at)}
                </DetailRow>
              </DetailGrid>
            </Section>

            <EarningsCards customerId={customerId} />
            <ReferralsSection customerId={customerId} />
          </div>
        )}
      </QueryState>
    </div>
  );
}

function EarningsCards({ customerId }: { customerId: string }) {
  const { defaultCurrency } = useAuth();
  const query = useReferrerEarnings(customerId);

  if (query.isLoading) return <LoadingRows rows={1} />;
  if (query.isError)
    return <ErrorInline error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data) return null;
  const e = query.data;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard
        label="Total earned"
        value={formatMicros(e.total_earned_micros, defaultCurrency)}
      />
      <StatCard
        label="Referred spend"
        value={formatMicros(e.total_referred_spend_micros, defaultCurrency)}
      />
      <StatCard label="Total referrals" value={formatEventCount(e.total_referrals)} />
      <StatCard
        label="Active referrals"
        value={formatEventCount(e.active_referrals)}
      />
    </div>
  );
}

function ReferralsSection({ customerId }: { customerId: string }) {
  const { defaultCurrency } = useAuth();
  const pager = useReferrerReferrals(customerId);
  const revoke = useRevokeReferral(customerId);

  return (
    <Section
      title="Referrals"
      description="Customers this referrer has brought in."
    >
      {pager.isLoading ? (
        <LoadingRows rows={4} />
      ) : pager.isError ? (
        <ErrorInline error={pager.error} onRetry={pager.refetch} />
      ) : pager.items.length === 0 ? (
        <EmptyState
          title="No referrals yet"
          description="Attributed customers will appear here as they sign up."
        />
      ) : (
        <div className="space-y-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Referred customer</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Reward model</TableHead>
                <TableHead className="text-right">Earned</TableHead>
                <TableHead className="text-right">Referred spend</TableHead>
                <TableHead>Attributed</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pager.items.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <div className="font-medium">
                      {r.referred_external_id || "—"}
                    </div>
                    <div className="font-mono text-xs text-muted-foreground">
                      {r.referred_customer_id}
                    </div>
                  </TableCell>
                  <TableCell>
                    <StatusBadge value={r.status} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge value={r.reward_type} tone="neutral" />
                  </TableCell>
                  <TableCell className="text-right">
                    {formatMicros(r.total_earned_micros, defaultCurrency)}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {formatMicros(r.total_referred_spend_micros, defaultCurrency)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatShortDate(r.attributed_at)}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1">
                      <ReferralLedgerDialog
                        referralId={r.id}
                        trigger={
                          <Button variant="ghost" size="sm">
                            <ScrollText />
                            Ledger
                          </Button>
                        }
                      />
                      <ConfirmDialog
                        destructive
                        title="Revoke this referral?"
                        description="Reward accrual stops and the attribution is removed. This can't be undone."
                        confirmLabel="Revoke referral"
                        onConfirm={async () => {
                          await revoke.mutateAsync(r.id);
                        }}
                        trigger={
                          <Button variant="ghost" size="sm">
                            <Ban />
                            Revoke
                          </Button>
                        }
                      />
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <CursorPagerControls pager={pager} />
        </div>
      )}
    </Section>
  );
}
